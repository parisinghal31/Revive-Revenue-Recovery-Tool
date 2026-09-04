"""Voice agent layer (Vapi).

/vapi/tools is the server endpoint the Vapi assistant calls mid-conversation:
  - tool-calls (apply_discount / send_upi_link / opt_out / schedule_retry):
    every tool passes through guardrails — the LLM has NO direct money authority.
  - transcript: final lines stream to the dashboard with intent chips.
  - status-update: drives the dashboard's live-call indicator.

The assistant is built inline per call (build_vapi_assistant) — no Vapi
dashboard config needed. Browser calls use the @vapi-ai/web SDK with the
config served by web_call_config().
"""
import os

from . import db, engine, guardrails, whatsapp
from .events import audit, hub

VAPI_SYSTEM_PROMPT = """You are 'Asha', a warm payment-recovery assistant for Tomato (food delivery).
Speak natural Hinglish (Hindi in Latin script mixed with English). Keep every reply under 2 sentences.

Context: the customer's payment of ₹{amount} for order {order_id} just failed ({error_code}).
Goal: help them complete the payment. You may use tools; you have NO other authority.

STRICT RULES:
1. Negotiation ladder: first empathy (no discount) → 5% → 10%. NEVER exceed 10%. If asked for more, politely refuse.
2. If the customer says anything like "call mat karo", "stop calling", "band karo" — apologize once, call the opt_out tool, then use the endCall tool immediately.
3. If they mention no money / "paise nahi hai" — call schedule_retry for salary day, reassure them, end warmly.
4. If card issues — call send_upi_link and tell them a WhatsApp link is coming.
4b. If the customer says they just paid ("kar diya", "ho gaya", "paid") — call check_payment_status. If paid=true, celebrate briefly ("Payment mil gaya!") and thank them; if false, say it hasn't reflected yet and they can retry the link.
5. If the customer switches language (English/Tamil), switch with them.
6. Never mention you are an AI unless asked directly; if asked, answer honestly.
7. When the conversation is complete — customer agreed, link sent, retry scheduled, or they say goodbye ("bye", "theek hai", "rakh do", "thank you", "ok done") — say ONE short goodbye line and immediately use the endCall tool. Never keep the line open after the customer is done.
"""

# intent tag -> detector keywords (fallback when the LLM classifier is keyless)
INTENTS = {
    "PRICE_OBJECTION": ["mehanga", "expensive", "costly", "zyada"],
    "OPT_OUT": ["mat karo", "stop calling", "band karo", "call mat"],
    "NO_FUNDS": ["paise nahi", "salary", "baad mein"],
    "AGREEMENT": ["theek hai", "ok", "haan", "kar do", "chalega"],
}


def tag_intent(text: str) -> str | None:
    from . import llm
    if llm.available():
        intent = llm.classify_intent(text)
        if intent and intent != "OTHER":
            return intent
    t = text.lower()
    for intent, kws in INTENTS.items():
        if any(k in t for k in kws):
            return intent
    return None


def transcript_line(failure_id: str, speaker: str, text: str) -> None:
    hub.broadcast({"type": "transcript", "data": {
        "failure_id": failure_id, "speaker": speaker, "text": text,
        "intent": tag_intent(text) if speaker == "customer" else None,
        "ts": db.now(),
    }})


# ---------- Vapi server-tool handlers ----------

def tool_apply_discount(failure_id: str, pct: float) -> dict:
    if not guardrails.check_discount(failure_id, pct).allowed:
        return {"ok": False, "say": f"Discount {pct}% is above my authority. Maximum I can offer is {guardrails.MAX_DISCOUNT_PCT}%."}
    f = db.one("SELECT * FROM failures WHERE id=?", (failure_id,))
    new_amt = int(round(f["amount"] * (1 - pct / 100)))
    audit("action", f"Negotiated {pct:g}% discount approved within ceiling — new amount ₹{new_amt/100:,.0f}",
          failure_id=failure_id, rule="MAX_DISCOUNT", outcome="PASSED",
          detail={"pct": pct, "new_amount": new_amt})
    db.set_setting(f"discount_{failure_id}", str(pct))
    return {"ok": True, "new_amount_paise": new_amt, "say": f"{pct:g}% discount applied."}


def tool_send_upi_link(failure_id: str) -> dict:
    link = f"/pay/{failure_id}"
    audit("action", f"UPI pivot: recovery link {link} sent on WhatsApp mid-call",
          failure_id=failure_id, outcome="INFO", detail={"link": link})
    f = db.one("SELECT * FROM failures WHERE id=?", (failure_id,))
    if f:
        whatsapp.send_recovery_link(f)
    return {"ok": True, "link": link, "say": "Maine WhatsApp par link bhej diya hai."}


def tool_opt_out(failure_id: str) -> dict:
    f = db.one("SELECT * FROM failures WHERE id=?", (failure_id,))
    guardrails.opt_out(f["customer_phone"], failure_id, "customer requested no contact on call")
    db.conn().execute("UPDATE failures SET status='lost' WHERE id=?", (failure_id,))
    db.conn().commit()
    hub.broadcast({"type": "failure_update", "data": {"id": failure_id, "status": "lost"}})
    return {"ok": True, "say": "Opt-out registered. Ending call."}


def tool_schedule_retry(failure_id: str) -> dict:
    f = db.one("SELECT * FROM failures WHERE id=?", (failure_id,))
    return engine.schedule_retry(f)


def tool_check_payment_status(failure_id: str) -> dict:
    f = db.one("SELECT * FROM failures WHERE id=?", (failure_id,))
    if not f:
        return {"ok": False, "error": "unknown failure"}
    paid = f["status"] == "recovered"
    rec = db.one("SELECT * FROM recoveries WHERE failure_id=?", (failure_id,)) if paid else None
    audit("action", f"Payment status checked on call: {'PAID ✓' if paid else 'not yet received'}",
          failure_id=failure_id, outcome="PASSED" if paid else "INFO",
          detail={"paid": paid})
    return {"ok": True, "paid": paid,
            "amount_paise": rec["amount_recovered"] if rec else None,
            "say": "Payment mil gaya, dhanyavaad!" if paid else "Abhi tak payment nahi aaya."}


TOOLS = {
    "apply_discount": lambda fid, args: tool_apply_discount(fid, float(args.get("pct", 5))),
    "send_upi_link": lambda fid, args: tool_send_upi_link(fid),
    "opt_out": lambda fid, args: tool_opt_out(fid),
    "schedule_retry": lambda fid, args: tool_schedule_retry(fid),
    "check_payment_status": lambda fid, args: tool_check_payment_status(fid),
}


def handle_vapi_webhook(body: dict) -> dict:
    """Vapi server messages -> tools through guardrails, transcripts/status to the dashboard."""
    message = body.get("message", {})
    mtype = message.get("type")
    failure_id = ((message.get("call", {}).get("metadata", {}) or {})
                  or (message.get("assistant", {}).get("metadata", {}) or {})).get("failure_id", "")

    if mtype == "transcript":
        if message.get("transcriptType") == "final" and message.get("transcript"):
            speaker = "agent" if message.get("role") == "assistant" else "customer"
            transcript_line(failure_id, speaker, message["transcript"])
        return {"ok": True}

    if mtype == "status-update":
        status = message.get("status")
        if status == "in-progress":
            hub.broadcast({"type": "call_started", "data": {"failure_id": failure_id}})
        elif status == "ended":
            hub.broadcast({"type": "call_ended", "data": {"failure_id": failure_id}})
        return {"ok": True}

    results = []
    for tc in message.get("toolCallList", []):
        name = tc.get("name") or tc.get("function", {}).get("name")
        args = tc.get("arguments") or tc.get("function", {}).get("arguments") or {}
        fn = TOOLS.get(name)
        out = fn(failure_id, args) if fn else {"ok": False, "error": f"unknown tool {name}"}
        results.append({"toolCallId": tc.get("id"), "result": db.dumps(out)})
    return {"results": results}


# ---------- assistant config ----------

VAPI_TOOL_DEFS = [
    {"name": "apply_discount", "description": "Apply a discount percentage to the failed order. Ceiling is enforced server-side.",
     "parameters": {"type": "object", "properties": {"pct": {"type": "number", "description": "discount percent, max 10"}}, "required": ["pct"]}},
    {"name": "send_upi_link", "description": "Send the customer a WhatsApp link to pay via UPI.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "opt_out", "description": "Customer asked to stop being contacted. Registers opt-out and ends the call.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "schedule_retry", "description": "Schedule a payment retry (salary day for insufficient funds).",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "check_payment_status", "description": "Check whether the customer's payment has landed. Use when they say they just paid.",
     "parameters": {"type": "object", "properties": {}}},
]


def build_vapi_assistant(f: dict, public_url: str) -> dict:
    """Transient inline assistant — no Vapi dashboard config needed."""
    prompt = VAPI_SYSTEM_PROMPT.format(
        amount=f"{f['amount'] / 100:,.0f}", order_id=f["order_id"], error_code=f["error_code"])
    return {
        "firstMessage": f"Namaste {f['customer_name']} ji! Main Asha bol rahi hoon Tomato se.",
        "model": {
            "provider": "openai", "model": "gpt-4o-mini",
            "messages": [{"role": "system", "content": prompt}],
            "tools": [{"type": "function", "function": t, "server": {"url": f"{public_url}/vapi/tools"}}
                      for t in VAPI_TOOL_DEFS] + [{"type": "endCall"}],
        },
        "voice": {"provider": "vapi", "voiceId": "Naina", "speed": 0.85},  # natural Hinglish, slightly slowed
        "transcriber": {"provider": "deepgram", "model": "nova-2", "language": "hi"},
        "server": {"url": f"{public_url}/vapi/tools"},
        "serverMessages": ["transcript", "status-update", "tool-calls"],
        "metadata": {"failure_id": f["id"]},
        # bounded call: hang up after 15s of silence, hard cap 5 min
        "silenceTimeoutSeconds": 15,
        "maxDurationSeconds": 300,
    }


def sip_configured() -> bool:
    return bool(os.environ.get("VAPI_API_KEY") and os.environ.get("VAPI_SIP_NUMBER_ID")
                and os.environ.get("CUSTOMER_SIP_URI"))


def place_sip_call(failure_id: str) -> dict:
    """Real outbound ring via Vapi SIP: Asha dials the customer's SIP address
    (a free Linphone account on the demo phone) — the phone rings like a call.
    Free numbers can't dial +91 PSTN; SIP-to-SIP is unrestricted and costs 0."""
    import json as _json
    import urllib.request
    f = db.one("SELECT * FROM failures WHERE id=?", (failure_id,))
    if not f:
        return {"error": "unknown failure"}
    public_url = os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")
    body = {
        "phoneNumberId": os.environ["VAPI_SIP_NUMBER_ID"],
        "assistant": build_vapi_assistant(f, public_url),
        "customer": {"sipUri": os.environ["CUSTOMER_SIP_URI"]},
    }
    req = urllib.request.Request(
        "https://api.vapi.ai/call", data=_json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {os.environ['VAPI_API_KEY']}",
                 "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Revive/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = _json.loads(r.read())
        audit("action", "REAL call ringing on customer's phone (Vapi SIP — free-tier PSTN workaround, disclosed)",
              failure_id=failure_id, outcome="INFO", detail={"vapi_call_id": out.get("id")})
        return {"ok": True, "vapi_call_id": out.get("id")}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        audit("system", f"SIP call failed: HTTP {e.code}", failure_id=failure_id,
              outcome="BLOCKED", detail={"body": detail})
        return {"error": f"Vapi HTTP {e.code}", "detail": detail}


# ─── PRODUCTION PATH (reference, not active on free tier) ────────────────────
# Real PSTN calls to +91 numbers need a telephony number Vapi can dial from
# (imported Twilio/Plivo number — trial accounts cannot provision one). With a
# paid number imported into Vapi as VAPI_PHONE_NUMBER_ID, the outbound call is
# identical to place_sip_call() with one line changed:
#
#     body = {
#         "phoneNumberId": os.environ["VAPI_PHONE_NUMBER_ID"],
#         "assistant": build_vapi_assistant(f, public_url),
#         "customer": {"number": f["customer_phone"]},   # PSTN instead of sipUri
#     }
#
# Everything else — assistant, tools, guardrails, transcripts, auto-hangup —
# is shared. The SIP path exists so the full call experience is demonstrable
# at ₹0; it is disclosed as a workaround in every audit row it writes.
# ─────────────────────────────────────────────────────────────────────────────


def web_call_config(failure_id: str) -> dict:
    """Config for a browser-based Vapi web call, used by /call/[id] via @vapi-ai/web."""
    public_url = os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")
    f = db.one("SELECT * FROM failures WHERE id=?", (failure_id,))
    if not f:
        return {"error": "unknown failure"}
    return {"assistant": build_vapi_assistant(f, public_url)}

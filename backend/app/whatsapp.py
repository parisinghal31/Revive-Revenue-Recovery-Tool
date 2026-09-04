"""Real WhatsApp sends via Twilio's WhatsApp Sandbox (free on trial accounts).

Env:
  TWILIO_SID / TWILIO_TOKEN  — account credentials
  TWILIO_WA_FROM             — sandbox number, usually whatsapp:+14155238886
  FRONTEND_URL               — public URL of the storefront (tunnel), so links
                               in messages open on a real phone

Recipients must have joined the sandbox first (send "join <code>" on WhatsApp
to the sandbox number — code shown in Twilio Console → Messaging → Try it out).
Without env config, send() is a no-op and the demo's simulated broadcast stands.
"""
import base64
import json
import os
import urllib.parse
import urllib.request

from . import db
from .events import audit

# Twilio rejections that are the free/trial tier talking, not a broken integration.
# Worth spelling out in the audit trail: the agent decided correctly and every
# guardrail passed — only the delivery transport is capped.
TWILIO_FREE_TIER = {
    "63007": "recipient has not joined the WhatsApp sandbox — they must send "
             "\"join <code>\" to the sandbox number first",
    "63015": "sandbox can only message numbers that have joined it",
    "63016": "free-form message outside the 24h customer-initiated window — a paid "
             "sender with a Meta-approved template is required",
    "63018": "sandbox daily message cap reached",
    "21608": "trial account can only message verified numbers",
    "21610": "recipient has unsubscribed from this sandbox number",
    "572002": "trial account has no phone number assigned for this destination — "
              "add the recipient as a verified number in the Twilio Console",
}


def _twilio_error(raw: str) -> tuple[str | None, str]:
    try:
        body = json.loads(raw)
    except ValueError:
        return None, ""
    code = body.get("code")
    return (str(code) if code is not None else None), (body.get("message") or "")


# Batch runs flip this on so synthetic records never trigger real messages/calls.
suppress_external = False


def configured() -> bool:
    return bool(os.environ.get("TWILIO_SID") and os.environ.get("TWILIO_TOKEN"))


def callmebot_configured() -> bool:
    return bool(os.environ.get("CALLMEBOT_PHONE") and os.environ.get("CALLMEBOT_APIKEY"))


def meta_configured() -> bool:
    return bool(os.environ.get("META_WA_TOKEN") and os.environ.get("META_WA_PHONE_ID"))


def greenapi_configured() -> bool:
    return bool(os.environ.get("GREEN_ID") and os.environ.get("GREEN_TOKEN"))


def frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")


def send_textmebot(body: str, failure_id: str | None = None) -> dict:
    """TextMeBot — CallMeBot-style bridge: the user's own WhatsApp (linked via QR)
    sends to the demo phone. Their server 411s python-urllib GETs, so use
    http.client with an explicit Content-Length header."""
    import http.client
    path = ("/send.php?"
            + urllib.parse.urlencode({"recipient": os.environ["TEXTMEBOT_PHONE"],
                                      "apikey": os.environ["TEXTMEBOT_APIKEY"], "text": body}))
    try:
        conn = http.client.HTTPSConnection("api.textmebot.com", timeout=40)
        conn.request("GET", path, headers={"User-Agent": "curl/8.0", "Accept": "*/*",
                                           "Content-Length": "0"})
        page = conn.getresponse().read().decode(errors="ignore")
        conn.close()
        ok = "success" in page.lower() or "queued" in page.lower() or (
            "sent" in page.lower() and "error" not in page.lower())
        audit("action",
              "REAL WhatsApp sent to demo phone (TextMeBot bridge — production: verified WABA sender)"
              if ok else "WhatsApp send FAILED (TextMeBot rejected the request)",
              failure_id=failure_id, outcome="PASSED" if ok else "BLOCKED",
              detail={"provider": "textmebot", "ok": ok})
        return {"ok": ok}
    except Exception as e:
        audit("system", f"WhatsApp send FAILED (TextMeBot unreachable: {e})",
              failure_id=failure_id, outcome="BLOCKED")
        return {"error": str(e)}


def send_callmebot(body: str, failure_id: str | None = None) -> dict:
    """Demo bridge: real WhatsApp to the registered demo phone via CallMeBot
    (free, personal-use API). Every message lands on the phone playing the
    customer, whatever number the failure record carries — disclosed in audit.
    Production path is a verified WhatsApp Business sender (Twilio/Meta)."""
    phone = os.environ["CALLMEBOT_PHONE"]
    url = ("https://api.callmebot.com/whatsapp.php?"
           + urllib.parse.urlencode({"phone": phone, "text": body,
                                     "apikey": os.environ["CALLMEBOT_APIKEY"]}))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Revive/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read().decode(errors="ignore")
        ok = "queued" in page.lower() or "sent" in page.lower()
        audit("action",
              "REAL WhatsApp sent to demo phone (CallMeBot bridge — production would use a verified WABA sender)"
              if ok else "WhatsApp send FAILED (CallMeBot rejected the request)",
              failure_id=failure_id, outcome="PASSED" if ok else "BLOCKED",
              detail={"provider": "callmebot", "ok": ok})
        return {"ok": ok}
    except Exception as e:
        audit("system", f"WhatsApp send FAILED (CallMeBot unreachable: {e})",
              failure_id=failure_id, outcome="BLOCKED")
        return {"error": str(e)}


def _json_call(url: str, payload: dict, headers: dict, provider: str,
               failure_id: str | None, ok_check) -> dict:
    import json
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0 Revive/1.0", **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            out = json.loads(r.read())
        ok = ok_check(out)
        audit("action",
              f"REAL WhatsApp sent via {provider}" if ok else f"WhatsApp send FAILED ({provider} rejected)",
              failure_id=failure_id, outcome="PASSED" if ok else "BLOCKED",
              detail={"provider": provider, "ok": ok})
        return {"ok": ok, "response": out}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        audit("system", f"WhatsApp send FAILED ({provider} HTTP {e.code})",
              failure_id=failure_id, outcome="BLOCKED", detail={"body": detail})
        return {"error": f"HTTP {e.code}", "detail": detail}
    except Exception as e:  # transport failure must not propagate into the engine
        audit("system", f"WhatsApp send FAILED ({provider} unreachable: {e})",
              failure_id=failure_id, outcome="BLOCKED", detail={"transport_error": str(e)})
        return {"error": "transport", "detail": str(e)}


def send_meta(to_phone: str, body: str, failure_id: str | None = None) -> dict:
    """Meta WhatsApp Cloud API (official, free): sends from the app's test business
    number. Free-form text needs an open 24h session (recipient messaged the test
    number that day) and the recipient added to the app's allowed list."""
    to = os.environ.get("META_WA_TO") or to_phone  # demo: override recipient to your phone
    return _json_call(
        f"https://graph.facebook.com/v21.0/{os.environ['META_WA_PHONE_ID']}/messages",
        {"messaging_product": "whatsapp", "to": to.lstrip("+"),
         "type": "text", "text": {"preview_url": True, "body": body}},
        {"Authorization": f"Bearer {os.environ['META_WA_TOKEN']}"},
        "Meta Cloud API", failure_id, lambda o: bool(o.get("messages")))


def send_greenapi(body: str, failure_id: str | None = None) -> dict:
    """Green API: a real WhatsApp account (linked once via QR) is the sender;
    messages go to the demo phone in GREEN_TO. Personal-account bridge — demo
    only, disclosed in audit; production uses a verified WABA sender."""
    to = os.environ["GREEN_TO"].lstrip("+")
    return _json_call(
        f"https://api.green-api.com/waInstance{os.environ['GREEN_ID']}/sendMessage/{os.environ['GREEN_TOKEN']}",
        {"chatId": f"{to}@c.us", "message": body},
        {}, "Green API bridge (demo — production: verified WABA sender)",
        failure_id, lambda o: bool(o.get("idMessage")))


def send(to_phone: str, body: str, failure_id: str | None = None) -> dict:
    """Send a real WhatsApp message. Providers in preference order (first configured
    wins): Meta Cloud API > Green API > CallMeBot > Twilio. Returns {ok}/{error}."""
    if suppress_external:
        return {"ok": False, "skipped": "batch mode — external sends suppressed"}
    if meta_configured():
        return send_meta(to_phone, body, failure_id)
    if greenapi_configured() and os.environ.get("GREEN_TO"):
        return send_greenapi(body, failure_id)
    if os.environ.get("TEXTMEBOT_PHONE") and os.environ.get("TEXTMEBOT_APIKEY"):
        return send_textmebot(body, failure_id)
    if callmebot_configured():
        return send_callmebot(body, failure_id)
    if not configured():
        audit("system", "WhatsApp NOT sent — no provider configured. Agent decision and guardrails stand.",
              failure_id=failure_id, outcome="BLOCKED", detail={"reason": "no provider configured"})
        return {"ok": False, "skipped": "whatsapp not configured"}
    sid = os.environ["TWILIO_SID"]
    token = os.environ["TWILIO_TOKEN"]
    wa_from = os.environ.get("TWILIO_WA_FROM", "whatsapp:+14155238886")
    # Failure records carry synthetic customer numbers; the sandbox can only reach
    # a number that has joined it. TWILIO_WA_TO redirects to the demo phone, the
    # same way META_WA_TO / GREEN_TO / CALLMEBOT_PHONE do — disclosed in audit.
    redirected = os.environ.get("TWILIO_WA_TO")
    to = redirected or to_phone

    data = urllib.parse.urlencode({
        "From": wa_from,
        "To": to if to.startswith("whatsapp:") else f"whatsapp:{to}",
        "Body": body,
    }).encode()
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=data,
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read())
        audit("action", f"REAL WhatsApp sent to {to[-4:].rjust(10, '*')} (sid {out.get('sid', '?')[:10]}…)"
                        + (" — demo phone, redirected from the synthetic customer number" if redirected else ""),
              failure_id=failure_id, outcome="PASSED",
              detail={"status": out.get("status"), "redirected_to_demo_phone": bool(redirected)})
        return {"ok": True, "sid": out.get("sid")}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        code, tw_msg = _twilio_error(detail)
        limitation = TWILIO_FREE_TIER.get(code or "")
        if limitation:
            message = (f"WhatsApp NOT delivered — Twilio free-tier limitation [{code}]: {limitation}. "
                       "Agent decision and all guardrails passed; only the delivery transport is capped.")
        else:
            message = (f"WhatsApp send FAILED (HTTP {e.code}"
                       f"{f', Twilio {code}' if code else ''}) — {tw_msg or 'see detail'}")
        audit("system", message, failure_id=failure_id, outcome="BLOCKED",
              detail={"http": e.code, "twilio_code": code, "free_tier_limit": bool(limitation),
                      "body": detail})
        return {"error": f"HTTP {e.code}", "twilio_code": code,
                "free_tier_limit": bool(limitation), "detail": detail}
    except Exception as e:  # TLS handshake, DNS, timeout — transport, not policy
        audit("system", f"WhatsApp NOT delivered — Twilio unreachable ({type(e).__name__}: {e}). "
                        "Agent decision and guardrails stand; delivery transport failed.",
              failure_id=failure_id, outcome="BLOCKED", detail={"transport_error": str(e)})
        return {"error": "transport", "detail": str(e)}


# ─── PRODUCTION PATH (reference, not active on free tier) ────────────────────
# In production, business-initiated WhatsApp messages MUST come from a verified
# WhatsApp Business sender using a pre-approved template (Meta policy — free-form
# text is only allowed inside a customer-initiated 24h session). With a paid
# Twilio account + an approved Utility template carrying {{1}}=name, {{2}}=amount,
# {{3}}=link, the send becomes:
#
# def send_template(to_phone: str, name: str, amount: str, link: str,
#                   failure_id: str | None = None) -> dict:
#     data = urllib.parse.urlencode({
#         "From": os.environ["TWILIO_WA_FROM"],          # verified WABA sender
#         "To": f"whatsapp:{to_phone}",
#         "ContentSid": os.environ["TWILIO_TEMPLATE_SID"],  # approved HX… template
#         "ContentVariables": json.dumps({"1": name, "2": amount, "3": link}),
#     }).encode()
#     req = urllib.request.Request(
#         f"https://api.twilio.com/2010-04-01/Accounts/{os.environ['TWILIO_SID']}/Messages.json",
#         data=data, headers={"Authorization": f"Basic {auth}",
#                             "Content-Type": "application/x-www-form-urlencoded"},
#         method="POST")
#     ...  # same audited response handling as send() above
#
# The demo bridges above exist only because trial accounts cannot get templates
# approved; the message content, guardrails, and audit trail are identical.
# ─────────────────────────────────────────────────────────────────────────────


def send_recovery_link(f: dict) -> dict:
    link = f"{frontend_url()}/pay/{f['id']}"
    discount = float(db.setting(f"discount_{f['id']}", "0"))
    amt = f"₹{int(round(f['amount'] * (1 - discount / 100))) / 100:,.0f}"
    body = (f"Hi {f['customer_name']}! 🍅 Your Tomato payment didn't go through — no worries.\n"
            + (f"Good news: a {discount:g}% discount is applied! " if discount else "")
            + f"Complete your {amt} order in one tap with UPI:\n{link}")
    return send(f["customer_phone"], body, f["id"])


def send_mandate_link(f: dict) -> dict:
    link = f"{frontend_url()}/restart-autopay/{f['id']}"
    body = (f"Hi {f['customer_name']}! Your Tomato Gold autopay was cancelled — your perks end soon. 😢\n"
            f"Restart in one tap to keep free delivery + 10% off:\n{link}")
    return send(f["customer_phone"], body, f["id"])

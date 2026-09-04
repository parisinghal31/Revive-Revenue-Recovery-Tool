"""LLM reasoning layer — 'LLM proposes, rules dispose'.

A real model reasons over each live failure and proposes an intervention from a
bounded menu. The proposal is validated against the allowed action set and then
passes through the deterministic guardrail layer before anything executes —
the LLM never touches money directly.

Providers (OpenAI-compatible chat endpoints), first key found wins:
  GROQ_API_KEY    -> Groq  (llama-3.3-70b-versatile, free tier, very fast)
  GEMINI_API_KEY  -> Google Gemini (gemini-2.0-flash via OpenAI-compat endpoint)

No key -> callers fall back to the static policy table (audited as such).
"""
import json
import logging
import os
import urllib.request

ALLOWED_ACTIONS = {"voice_call", "whatsapp_link", "schedule_retry", "bank_hold", "mandate_save"}


def _provider():
    if os.environ.get("GROQ_API_KEY"):
        return ("https://api.groq.com/openai/v1/chat/completions",
                os.environ["GROQ_API_KEY"], "openai/gpt-oss-120b", "groq/gpt-oss-120b")
    if os.environ.get("GEMINI_API_KEY"):
        return ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                os.environ["GEMINI_API_KEY"], "gemini-2.0-flash", "gemini-2.0-flash")
    return None


def available() -> bool:
    return _provider() is not None


def model_name() -> str:
    p = _provider()
    return p[3] if p else "policy-table"


def _chat(system: str, user: str, max_tokens: int = 400) -> str | None:
    p = _provider()
    if not p:
        return None
    url, key, model, _ = p
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 Revive/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read())
        return out["choices"][0]["message"]["content"]
    except Exception:
        # Never fatal: the caller falls back to the deterministic policy table and
        # audits it. Logged so a hosted deploy can tell "LLM down" from "LLM off".
        log.warning("LLM call failed; falling back to the policy table", exc_info=True)
        return None


log = logging.getLogger("revive.llm")


DECIDE_SYSTEM = """You are the decision brain of Revive, an AI revenue-recovery agent for Indian payment failures on Razorpay.
Given a failed payment, diagnose the root cause and pick ONE intervention from this bounded menu:
- voice_call: outbound Hinglish call with bounded negotiation (best for hesitation/drop-off; intrusive, use when human touch recovers most)
- whatsapp_link: send a payment link, suggest UPI as alternate method (low friction, best for card problems or bank declines)
- schedule_retry: silent auto-retry, no customer contact (best for transient gateway errors; for insufficient funds schedule for salary day, the 1st)
- bank_hold: freeze ALL retries for this bank until it recovers (ONLY when the issuer bank itself is down)
- mandate_save: subscription churn outreach with autopay restart link (ONLY for cancelled mandates)

Channel priors from recovery data — start from these, deviate only with a concrete reason (tiny amount, suspicious velocity):
- AUTHENTICATION_FAILED / CHECKOUT_ABANDONED are HESITATION signals: the customer chose not to finish. A human-touch call converts these far better than a link — prefer voice_call for amounts above ~₹500.
- Card-problem codes (CARD_EXPIRED, PAYMENT_DECLINED, TXN_LIMIT_EXCEEDED, BAD_REQUEST_ERROR): whatsapp_link with UPI pivot.
- Transient gateway noise (GATEWAY_ERROR, SERVER_ERROR): schedule_retry, never bother the customer.

Calling hours are NOT your decision. A deterministic guardrail owns them: the merchant's quiet window is given to you as quiet_window_ist, and a call chosen inside it is queued and placed automatically when the window closes — never dropped. quiet_hours_now tells you whether the current hour is inside it. Do NOT downgrade voice_call to a link because an hour feels late or intrusive; if the hour is outside quiet_window_ist it is an approved calling hour, whatever the clock says.

Also consider: amount, method, bank health, and how many times this customer already failed recently (velocity may mean fraud — suppression is a separate guardrail, but factor it into channel choice).

Respond ONLY with JSON: {"root_cause": "<bank|customer|gateway>", "action": "<one menu item>", "reasoning": "<2 sentences, concrete, why this beats the alternatives>", "confidence": <0-1>}"""


def decide(failure: dict, context: dict) -> dict | None:
    """Returns {root_cause, action, reasoning, confidence, model} or None (no key / error / invalid)."""
    user = json.dumps({
        "error_code": failure["error_code"],
        "amount_inr": round(failure["amount"] / 100),
        "method": failure["method"],
        "bank": failure["bank"],
        "kind": failure["kind"],
        "hour_ist": context.get("hour_ist"),
        "quiet_window_ist": context.get("quiet_window"),
        "quiet_hours_now": context.get("quiet_now"),
        "recent_failures_same_customer": context.get("recent_same_customer", 0),
        "bank_currently_held": context.get("bank_held", False),
    })
    raw = _chat(DECIDE_SYSTEM, user)
    if not raw:
        return None
    try:
        d = json.loads(raw)
        if d.get("action") not in ALLOWED_ACTIONS:
            return {"invalid": True, "proposed": d.get("action"), "reasoning": d.get("reasoning", "")}
        return {"root_cause": d.get("root_cause", "customer"), "action": d["action"],
                "reasoning": d.get("reasoning", ""), "confidence": d.get("confidence"),
                "model": model_name()}
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


INTENT_SYSTEM = """Classify one customer utterance from a payment-recovery call (Hinglish/English/Hindi).
Respond ONLY with JSON: {"intent": "<PRICE_OBJECTION|OPT_OUT|NO_FUNDS|AGREEMENT|QUESTION|OTHER>"}"""


def classify_intent(text: str) -> str | None:
    raw = _chat(INTENT_SYSTEM, json.dumps({"utterance": text}), max_tokens=30)
    if not raw:
        return None
    try:
        intent = json.loads(raw).get("intent")
        return intent if intent in {"PRICE_OBJECTION", "OPT_OUT", "NO_FUNDS", "AGREEMENT", "QUESTION", "OTHER"} else None
    except json.JSONDecodeError:
        return None

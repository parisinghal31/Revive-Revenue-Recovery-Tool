"""Real Razorpay test-mode integration.

Activates when RAZORPAY_KEY_ID + RAZORPAY_KEY_SECRET are set (test keys, rzp_test_*).
- create_order(): real Orders API call — the id it returns opens Razorpay's real Checkout.
- verify_signature(): HMAC-SHA256 webhook verification (RAZORPAY_WEBHOOK_SECRET).
- map_failure(): translates Razorpay's error taxonomy (error_code/source/step/reason)
  into Revive's decline codes so the decision engine works identically on real events.

Without keys, the storefront falls back to the simulated card picker.
"""
import base64
import hashlib
import hmac
import json
import os
import urllib.request


def keys() -> tuple[str, str] | None:
    kid, secret = os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")
    return (kid, secret) if kid and secret else None


def create_order(amount_paise: int, receipt: str) -> dict:
    k = keys()
    if not k:
        return {"error": "razorpay keys not configured"}
    auth = base64.b64encode(f"{k[0]}:{k[1]}".encode()).decode()
    body = json.dumps({"amount": amount_paise, "currency": "INR", "receipt": receipt})
    req = urllib.request.Request(
        "https://api.razorpay.com/v1/orders", data=body.encode(),
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json",
                 "User-Agent": "Revive/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"razorpay HTTP {e.code}", "detail": e.read().decode()[:300]}


def order_payments(order_id: str) -> list[dict]:
    k = keys()
    if not k:
        return []
    auth = base64.b64encode(f"{k[0]}:{k[1]}".encode()).decode()
    req = urllib.request.Request(
        f"https://api.razorpay.com/v1/orders/{order_id}/payments",
        headers={"Authorization": f"Basic {auth}", "User-Agent": "Revive/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read()).get("items", [])
    except urllib.error.HTTPError:
        return []


def verify_signature(raw_body: bytes, signature: str) -> bool | None:
    """True/False when a webhook secret is configured; None = verification unavailable."""
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        return None
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


# Razorpay failure taxonomy -> Revive decline codes (tolerant substring matching,
# since error_reason enums vary by method and gateway)
def map_failure(entity: dict) -> dict:
    reason = " ".join(str(entity.get(x, "")) for x in
                      ("error_code", "error_reason", "error_description", "error_step")).lower()
    if "authentication" in reason or "otp" in reason or "3ds" in reason:
        code = "AUTHENTICATION_FAILED"
    elif "insufficient" in reason:
        code = "INSUFFICIENT_FUNDS"
    elif "expired" in reason:
        code = "CARD_EXPIRED"
    elif "limit" in reason:
        code = "TXN_LIMIT_EXCEEDED"
    elif "gateway" in reason or "server" in reason or "timeout" in reason:
        code = "GATEWAY_ERROR"
    elif "declined" in reason or "failed" in reason:
        code = "PAYMENT_DECLINED"
    else:
        code = "PAYMENT_DECLINED"
    return {
        "customer_name": entity.get("notes", {}).get("customer_name") or "Customer",
        "customer_phone": entity.get("contact") or "+919999999999",
        "amount": int(entity.get("amount") or 0),
        "method": entity.get("method") or "card",
        "error_code": code,
        "bank": entity.get("bank") or entity.get("wallet") or "UNKNOWN",
        "order_id": entity.get("order_id") or "",
        "raw_error": {k: entity.get(k) for k in
                      ("error_code", "error_reason", "error_description", "error_source", "error_step")},
    }

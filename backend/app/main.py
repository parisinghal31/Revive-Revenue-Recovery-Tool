"""Revive backend — FastAPI app.

Run:  uvicorn app.main:app --reload --port 8000
"""
import asyncio
import json
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db, engine, guardrails, razorpay_gw, simulator, voice
from .events import hub, audit, metrics, push_metrics


log = logging.getLogger("revive")

QUIET_TICK_S = 60


async def _quiet_queue_ticker():
    """Watches for the quiet window closing so deferred calls actually go out."""
    while True:
        await asyncio.sleep(QUIET_TICK_S)
        try:
            await asyncio.to_thread(engine.release_quiet_queue)
        except Exception as e:  # a bad tick must never kill the loop
            audit("system", f"Quiet-queue ticker error: {e}", outcome="INFO")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    hub.register_loop(asyncio.get_running_loop())
    db.conn()  # ensure schema
    log.info("Revive online — db=%s", db.DB_PATH)
    audit("system", "Revive engine online — guardrails armed", outcome="INFO")
    ticker = asyncio.create_task(_quiet_queue_ticker())
    engine.release_quiet_queue()  # catch calls parked while the server was down
    yield
    ticker.cancel()


app = FastAPI(title="Revive — AI Revenue Recovery", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # storefront is served from localhost AND a public tunnel
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Liveness + readiness probe for the hosting platform.

    Reports WHICH optional integrations are configured, never their values. On a
    hosted box the audit trail lives in ephemeral SQLite, so this is the fastest
    way to see why a channel went quiet after a deploy.
    """
    try:
        db.conn().execute("SELECT 1")
    except Exception as e:
        log.exception("health: database unreachable")
        raise HTTPException(status_code=503, detail=f"database unreachable: {e}")
    return {
        "status": "ok",
        "database": "ok",
        "integrations": {
            "llm": bool(os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY")),
            "razorpay": bool(os.environ.get("RAZORPAY_KEY_ID")),
            "vapi": bool(os.environ.get("VAPI_API_KEY")),
            "whatsapp": bool(os.environ.get("META_WA_TOKEN") or os.environ.get("TWILIO_SID")
                             or os.environ.get("CALLMEBOT_APIKEY")),
        },
    }


# ---------- realtime ----------

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await hub.connect(websocket)
    try:
        await websocket.send_json({"type": "metrics", "data": metrics()})
        while True:
            await websocket.receive_text()  # keepalive pings from client
    except WebSocketDisconnect:
        hub.disconnect(websocket)


# ---------- webhook (Razorpay-shaped) ----------

@app.post("/webhook/razorpay")
async def webhook(request: Request):
    """One endpoint, two shapes:
    - REAL Razorpay webhook (test mode): {"entity":"event","event":"payment.failed",
      "payload":{"payment":{"entity":{...}}}} with X-Razorpay-Signature header.
    - Simulated events from the storefront/demo panel: {"event":..., "payload":{flat}}.
    """
    raw = await request.body()
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        body = {}
    event = body.get("event", "payment.failed")
    p = body.get("payload", {})

    # real Razorpay shape: payload.payment.entity
    entity = (p.get("payment") or {}).get("entity") if isinstance(p.get("payment"), dict) else None
    if entity:
        verified = razorpay_gw.verify_signature(raw, request.headers.get("X-Razorpay-Signature", ""))
        if verified is False:
            audit("system", "Webhook REJECTED: bad Razorpay signature", outcome="BLOCKED")
            return {"error": "invalid signature"}
        audit("system", f"Real Razorpay webhook received ({event})"
              + (" — signature verified" if verified else " — no webhook secret set, signature unchecked"),
              outcome="PASSED" if verified else "INFO")
        p = razorpay_gw.map_failure(entity)

    if event == "subscription.cancelled":
        p["error_code"] = "MANDATE_CANCELLED"
        p["kind"] = "subscription_cancelled"
    return engine.ingest_failure(p)


# ---------- real Razorpay test-mode checkout ----------

@app.get("/api/rzp-config")
def rzp_config():
    k = razorpay_gw.keys()
    return {"key_id": k[0] if k else None}


class OrderIn(BaseModel):
    amount: int  # paise


@app.post("/api/create-order")
def create_order(o: OrderIn):
    order = razorpay_gw.create_order(o.amount, receipt=db.new_id("rcpt"))
    if "id" in order:
        audit("system", f"Razorpay test-mode order created: {order['id']} for ₹{o.amount/100:,.0f}",
              outcome="INFO", detail={"order_id": order["id"]})
    return order


class ClientFailure(BaseModel):
    """Checkout.js payment.failed handler posts the raw error here instantly
    (the dashboard webhook arrives too, but this gives sub-second UX).
    `scenario` optionally overlays a specific decline reason — test mode only
    emits generic failures, so the taxonomy is enriched and audited as such."""
    error: dict = {}
    order_id: str = ""
    customer_name: str = "Customer"
    customer_phone: str = "+919999999999"
    amount: int = 0
    method: str = "card"
    scenario: str = ""


class CheckOrder(BaseModel):
    """Reload-safe reconciliation: after a redirect flow wipes the page, the
    checkout asks Razorpay what actually happened to the order."""
    order_id: str
    customer_name: str = "Customer"
    customer_phone: str = "+919999999999"
    amount: int = 0
    scenario: str = ""


@app.post("/api/check-order")
def check_order(c: CheckOrder):
    # already ingested (client event or webhook beat us to it)? return that outcome
    existing = db.one("SELECT * FROM failures WHERE order_id=?", (c.order_id,))
    if existing:
        act = db.one("SELECT * FROM actions WHERE failure_id=? ORDER BY created_at DESC", (existing["id"],))
        return {"status": "failed", "failure_id": existing["id"],
                "action": act["action_type"] if act else "none",
                "detail": json.loads(act["detail"]) if act else {}}

    payments = razorpay_gw.order_payments(c.order_id)
    if any(p.get("status") in ("captured", "authorized") for p in payments):
        return {"status": "paid"}
    failed = next((p for p in payments if p.get("status") == "failed"), None)
    if not failed:
        return {"status": "pending"}

    failed.setdefault("notes", {})["customer_name"] = c.customer_name
    failed["contact"] = failed.get("contact") or c.customer_phone
    failed["order_id"] = c.order_id
    mapped = razorpay_gw.map_failure(failed)
    audit("system", f"Order reconciliation: Razorpay reports payment {failed.get('id')} FAILED "
                    f"({failed.get('error_reason') or failed.get('error_code')})",
          outcome="INFO", detail=mapped["raw_error"])
    if c.scenario and c.scenario in engine.DECISION_TABLE:
        mapped["error_code"] = c.scenario
        audit("system", f"Decline-reason overlay: reconciled event enriched as {c.scenario}",
              outcome="INFO", detail={"scenario": c.scenario})
    res = engine.ingest_failure(mapped)
    return {"status": "failed", **res}


@app.post("/api/client-failure")
def client_failure(c: ClientFailure):
    meta = c.error.get("metadata", {}) if isinstance(c.error, dict) else {}
    entity = {
        "error_code": c.error.get("code"), "error_reason": c.error.get("reason"),
        "error_description": c.error.get("description"), "error_step": c.error.get("step"),
        "error_source": c.error.get("source"),
        "contact": c.customer_phone, "amount": c.amount, "method": c.method,
        "order_id": c.order_id or meta.get("order_id", ""),
        "notes": {"customer_name": c.customer_name},
    }
    mapped = razorpay_gw.map_failure(entity)
    audit("system", f"Real checkout failure (client event): {mapped['raw_error'].get('error_reason') or mapped['raw_error'].get('error_code')}",
          outcome="INFO", detail=mapped["raw_error"])
    if c.scenario and c.scenario in engine.DECISION_TABLE:
        mapped["error_code"] = c.scenario
        audit("system", f"Decline-reason overlay: real test-mode event enriched as {c.scenario} "
                        "(Razorpay test mode only emits generic failures — overlay is simulated, transport is real)",
              outcome="INFO", detail={"scenario": c.scenario})
    return engine.ingest_failure(mapped)


# ---------- dashboard sandbox: system events one checkout can't produce ----------

@app.post("/demo/fraud-burst")
def demo_fraud(phone: str = "+919900000099"):
    """Fires 5 rapid failures from one source — the 5th must be suppressed."""
    results = []
    for i in range(5):
        results.append(engine.ingest_failure({
            "customer_name": "UNKNOWN", "customer_phone": phone,
            "amount": 10000, "method": "card",
            "error_code": "PAYMENT_DECLINED", "bank": "AXIS",
        }))
    return {"results": results}


@app.post("/demo/outage")
def demo_outage(bank: str = "HDFC", n: int = 6):
    """Simulates an issuer outage: n ISSUER_DOWN failures, then recovery release."""
    ids = []
    for i in range(n):
        r = engine.ingest_failure({
            "customer_name": f"Customer{i+1}", "customer_phone": f"+9198000000{i:02d}",
            "amount": (i + 1) * 50000, "method": "card",
            "error_code": "ISSUER_DOWN", "bank": bank,
        })
        ids.append(r["failure_id"])
    return {"held": ids, "hint": f"POST /demo/outage-recover?bank={bank} to release"}


@app.post("/demo/outage-recover")
def demo_outage_recover(bank: str = "HDFC"):
    """'Bank up' from the dashboard: release holds and send each customer a UPI link."""
    return engine.release_bank_hold(bank, send_links=True)


class QuietHoursIn(BaseModel):
    start_h: int
    end_h: int


def _quiet_state() -> dict:
    start, end = guardrails.quiet_window()
    h = guardrails.current_ist_hour()
    return {"start_h": start, "end_h": end, "hour_ist": h,
            "in_quiet": guardrails.in_quiet_window(h),
            "default_start_h": guardrails.QUIET_START_H,
            "default_end_h": guardrails.QUIET_END_H}


@app.get("/api/quiet-hours")
def get_quiet_hours():
    return _quiet_state()


@app.post("/api/quiet-hours/release")
def release_quiet_queue():
    """Manual kick for the same release the ticker performs."""
    return engine.release_quiet_queue()


@app.post("/api/quiet-hours")
def set_quiet_hours(q: QuietHoursIn):
    """Merchant edits the TRAI window. Every change is audited — the compliance
    story is 'here is the window, and here is who moved it, when'."""
    before = guardrails.window_label()
    try:
        guardrails.set_quiet_window(q.start_h, q.end_h)
    except ValueError as e:
        return {"error": str(e)}
    after = guardrails.window_label()
    audit("system", f"TRAI quiet-hours window changed {before} -> {after} IST",
          rule="TRAI_QUIET_HOURS", outcome="INFO", detail={"from": before, "to": after})
    state = _quiet_state()
    hub.broadcast({"type": "quiet_hours", "data": state})
    # a narrowed window can put us outside quiet hours right now — release at once
    state["released"] = engine.release_quiet_queue().get("released", 0)
    return state


class ClockIn(BaseModel):
    hour: int | None = None  # None = real clock


@app.post("/demo/clock")
def demo_clock(c: ClockIn):
    if c.hour is None:
        db.conn().execute("DELETE FROM settings WHERE key='sim_hour'")
        db.conn().commit()
        audit("system", "Demo clock reset to real time", outcome="INFO")
        hub.broadcast({"type": "quiet_hours", "data": _quiet_state()})
        return {"sim_hour": None, "released": engine.release_quiet_queue().get("released", 0)}
    db.set_setting("sim_hour", str(c.hour))
    audit("system", f"Demo clock set to {c.hour}:00 IST", outcome="INFO", detail={"hour": c.hour})
    hub.broadcast({"type": "quiet_hours", "data": _quiet_state()})
    return {"sim_hour": c.hour, "released": engine.release_quiet_queue().get("released", 0)}


# merchant configuration, not demo state — a reset must not silently revert it
PRESERVED_SETTINGS = ("quiet_start_h", "quiet_end_h")


@app.post("/demo/reset")
def demo_reset():
    for t in ["failures", "actions", "audit_log", "blacklist", "recoveries"]:
        db.conn().execute(f"DELETE FROM {t}")
    placeholders = ",".join("?" * len(PRESERVED_SETTINGS))
    db.conn().execute(f"DELETE FROM settings WHERE key NOT IN ({placeholders})", PRESERVED_SETTINGS)
    db.conn().commit()
    audit("system", f"Demo state reset — tables cleared, quiet-hours window kept at {guardrails.window_label()} IST",
          outcome="INFO")
    push_metrics()
    return {"ok": True}


# ---------- voice ----------

class SipCallIn(BaseModel):
    failure_id: str


@app.post("/voice/sip-call")
def sip_call(s: SipCallIn):
    """Ring the demo phone for real via Vapi SIP (needs CUSTOMER_SIP_URI env)."""
    if not voice.sip_configured():
        return {"error": "SIP not configured — set VAPI_SIP_NUMBER_ID + CUSTOMER_SIP_URI"}
    return voice.place_sip_call(s.failure_id)


@app.post("/vapi/tools")
def vapi_tools(body: dict):
    return voice.handle_vapi_webhook(body)


@app.get("/voice/web-call-config/{failure_id}")
def web_call_cfg(failure_id: str):
    return voice.web_call_config(failure_id)


# ---------- batch ----------

class BatchIn(BaseModel):
    n: int = 500
    seed: int = 42


@app.post("/simulate/batch")
def run_batch(b: BatchIn):
    """Runs in a thread so the WebSocket keeps streaming while records flow."""
    result_holder: dict = {}

    def go():
        result_holder["report"] = simulator.run_batch(b.n, b.seed)

    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(timeout=120)
    return result_holder.get("report", {"status": "running"})


# ---------- recovery pages API ----------

@app.get("/api/failure/{failure_id}")
def get_failure(failure_id: str):
    f = db.one("SELECT * FROM failures WHERE id=?", (failure_id,))
    if not f:
        return {"error": "not found"}
    discount = float(db.setting(f"discount_{failure_id}", "0"))
    f["discount_pct"] = discount
    f["payable_paise"] = int(round(f["amount"] * (1 - discount / 100)))
    return f


class PayIn(BaseModel):
    failure_id: str
    channel: str = "whatsapp"


@app.post("/api/pay")
def pay(p: PayIn):
    """Customer completed payment on the recovery page (simulated UPI success)."""
    discount = float(db.setting(f"discount_{p.failure_id}", "0"))
    f = db.one("SELECT * FROM failures WHERE id=?", (p.failure_id,))
    is_mrr = bool(f and f["kind"] == "subscription_cancelled")
    return engine.record_recovery(p.failure_id, discount_pct=discount,
                                  channel="mandate_restart" if is_mrr else p.channel,
                                  is_mrr=is_mrr)


# ---------- dashboard API ----------

@app.get("/api/metrics")
def api_metrics():
    return metrics()


@app.get("/api/audit")
def api_audit(limit: int = 100):
    return db.rows("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,))


@app.get("/api/failures")
def api_failures(limit: int = 50):
    return db.rows("SELECT * FROM failures ORDER BY created_at DESC LIMIT ?", (limit,))


@app.get("/api/recovery-series")
def api_recovery_series():
    """Cumulative recovered paise over time — feeds the dashboard area chart."""
    rows = db.rows("SELECT created_at, amount_recovered FROM recoveries ORDER BY created_at")
    out, cum = [], 0
    for r in rows:
        cum += r["amount_recovered"]
        out.append({"t": r["created_at"], "cum_paise": cum})
    return out


@app.get("/api/bank-health")
def api_bank_health():
    holds = db.rows("SELECT key FROM settings WHERE key LIKE 'bank_hold_%'")
    return {"down": [h["key"].replace("bank_hold_", "") for h in holds]}

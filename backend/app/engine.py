"""Decision engine: decline code -> root cause -> bounded intervention.

This is the gap Revive fills: Razorpay's native retry is time-based (T+1/T+2/T+3)
regardless of WHY the payment failed. Revive diagnoses the decline code first —
retrying an expired card tomorrow is wasted; calling a hesitant customer works.

Every decision emits "brain" audit events (the dashboard's Agent Brain panel)
and passes through the guardrail layer before any action executes.
"""
from . import db, guardrails, llm, whatsapp
from .events import audit, hub, push_metrics

# Razorpay-style decline codes -> (root cause, intervention, reasoning shown in Agent Brain)
DECISION_TABLE = {
    "BAD_REQUEST_ERROR":        ("customer", "whatsapp_link",  "Customer-side input error — a fresh payment link removes friction. No call needed."),
    "GATEWAY_ERROR":            ("gateway",  "schedule_retry", "Gateway glitch, transient — silent auto-retry in 30 min. Contacting the customer would create doubt."),
    "SERVER_ERROR":             ("gateway",  "schedule_retry", "Processor error, transient — silent auto-retry. Not the customer's fault, don't bother them."),
    "AUTHENTICATION_FAILED":    ("customer", "voice_call",     "OTP/3DS abandoned mid-flow — classic hesitation. A human-sounding call recovers these best."),
    "PAYMENT_DECLINED":         ("bank",     "whatsapp_link",  "Issuer declined — suggest an alternate method (UPI) via WhatsApp link."),
    "INSUFFICIENT_FUNDS":       ("customer", "schedule_retry", "No balance today ≠ no intent. Schedule retry for the 1st (salary day) and inform politely."),
    "CARD_EXPIRED":             ("customer", "whatsapp_link",  "Retrying an expired card is ALWAYS wasted — send a link to pay with UPI/another card instead."),
    "ISSUER_DOWN":              ("bank",     "bank_hold",      "Issuer bank is down — retrying now burns goodwill. Hold ALL retries for this bank until it recovers."),
    "TXN_LIMIT_EXCEEDED":       ("bank",     "whatsapp_link",  "Daily limit hit — offer UPI (separate limit) via link."),
    "CHECKOUT_ABANDONED":       ("customer", "voice_call",     "Cart built, checkout opened, never paid — price hesitation. Call with bounded negotiation authority."),
    "MANDATE_CANCELLED":        ("customer", "mandate_save",   "Autopay mandate revoked — subscription churning. Reach out with a restart link before service lapses."),
}


def brain(failure_id: str, msg: str, detail: dict | None = None) -> None:
    audit("brain", msg, failure_id=failure_id, outcome="INFO", detail=detail)


def ingest_failure(payload: dict, use_llm: bool = True) -> dict:
    """Entry point: a payment.failed / subscription.cancelled style event arrives.

    Live traffic (use_llm=True): an LLM reasons over the failure and proposes the
    intervention from a bounded menu — validated, then guardrailed. Batch runs pass
    use_llm=False for reproducibility and rate limits; the audit trail says which
    path decided every case.
    """
    f = {
        "id": db.new_id("fail"),
        "created_at": db.now(),
        "order_id": payload.get("order_id", db.new_id("order")),
        "customer_name": payload.get("customer_name", "Customer"),
        "customer_phone": payload.get("customer_phone", "+919999999999"),
        "amount": int(payload.get("amount", 49900)),
        "method": payload.get("method", "card"),
        "error_code": payload.get("error_code", "GATEWAY_ERROR"),
        "error_source": None,
        "bank": payload.get("bank", "HDFC"),
        "kind": payload.get("kind", "payment_failed"),
        "status": "open",
    }

    # policy-table default (also the no-key / batch / LLM-error fallback)
    source, action_type, reasoning = DECISION_TABLE.get(
        f["error_code"], ("gateway", "schedule_retry", "Unknown code — conservative silent retry.")
    )
    decided_by = "policy-table"

    if use_llm and llm.available():
        hour_ist = guardrails.current_ist_hour()
        context = {
            "hour_ist": hour_ist,
            "quiet_window": guardrails.window_label(),
            "quiet_now": guardrails.in_quiet_window(hour_ist),
            "recent_same_customer": db.one(
                "SELECT COUNT(*) c FROM failures WHERE customer_phone=? AND created_at>=?",
                (f["customer_phone"], db.now() - 3600))["c"],
            "bank_held": db.setting(f"bank_hold_{f['bank']}") is not None,
        }
        proposal = llm.decide(f, context)
        if proposal and proposal.get("invalid"):
            brain(f["id"], f"LLM proposed out-of-menu action '{proposal['proposed']}' — REJECTED by policy validator, "
                           f"falling back to table. (Bounded actions mean bounded, even for the model.)")
        elif proposal:
            source, action_type = proposal["root_cause"], proposal["action"]
            reasoning = proposal["reasoning"]
            decided_by = proposal["model"]
        else:
            brain(f["id"], "LLM unavailable/timed out — deterministic policy table took over. Graceful degradation.")

    f["error_source"] = source
    db.insert("failures", f)
    hub.broadcast({"type": "failure", "data": f})

    amt = f"₹{f['amount'] / 100:,.0f}"
    brain(f["id"], f"Failure ingested: {amt} via {f['method']} — code {f['error_code']} (source: {source})",
          {"amount": f["amount"], "code": f["error_code"]})
    brain(f["id"], f"[{decided_by}] {reasoning}", {"decided_by": decided_by})

    return decide(f, action_type)


def decide(f: dict, action_type: str) -> dict:
    fid = f["id"]

    # Fraud check runs on EVERY failure before anything else.
    if not guardrails.check_fraud_velocity(fid, f["customer_phone"]).allowed:
        db.conn().execute("UPDATE failures SET status='suppressed' WHERE id=?", (fid,))
        db.conn().commit()
        brain(fid, "Recovery agent knows when NOT to recover: this money is not worth chasing. Case suppressed, risk team flagged.")
        hub.broadcast({"type": "failure_update", "data": {"id": fid, "status": "suppressed"}})
        push_metrics()
        return {"failure_id": fid, "action": "suppressed", "reason": "fraud velocity"}

    if action_type == "bank_hold":
        return bank_hold(f)
    if action_type in ("voice_call", "whatsapp_link", "mandate_save"):
        return contact_customer(f, action_type)
    if action_type == "schedule_retry":
        return schedule_retry(f)
    return {"failure_id": fid, "action": "none"}


def contact_customer(f: dict, action_type: str) -> dict:
    fid = f["id"]

    if not guardrails.check_blacklist(fid, f["customer_phone"]).allowed:
        _finish_action(f, action_type, "blocked", "opt-out blacklist")
        return {"failure_id": fid, "action": "halted", "reason": "opt-out"}

    if not guardrails.check_contact_budget(fid).allowed:
        _finish_action(f, action_type, "blocked", "contact budget")
        return {"failure_id": fid, "action": "blocked", "reason": "contact budget"}

    needs_call = action_type in ("voice_call", "mandate_save")
    if needs_call and not guardrails.check_quiet_hours(fid).allowed:
        db.conn().execute("UPDATE failures SET status='queued' WHERE id=?", (fid,))
        db.conn().commit()
        _record_action(f, action_type, "pending",
                       {"queued_until": f"{guardrails.quiet_window()[1]:02d}:00 IST"})
        brain(fid, "Action QUEUED, not sent — compliance is a feature, not a footnote.")
        hub.broadcast({"type": "failure_update", "data": {"id": fid, "status": "queued"}})
        return {"failure_id": fid, "action": "queued", "reason": "quiet hours"}

    detail = {}
    if action_type == "voice_call":
        detail = {"language": "hinglish", "max_discount_pct": guardrails.MAX_DISCOUNT_PCT}
        audit("action", f"Placing Hinglish voice call to {f['customer_name']} — negotiation ceiling {guardrails.MAX_DISCOUNT_PCT}%",
              failure_id=fid, outcome="INFO", detail=detail)
        from . import voice
        if voice.sip_configured() and not whatsapp.suppress_external:
            import threading
            threading.Thread(target=voice.place_sip_call, args=(fid,), daemon=True).start()
            detail["sip_ring"] = True
    elif action_type == "whatsapp_link":
        link = f"/pay/{fid}"
        detail = {"link": link}
        audit("action", f"WhatsApp recovery link sent: {link} (suggests UPI as alternate method)",
              failure_id=fid, outcome="INFO", detail=detail)
        whatsapp.send_recovery_link(f)
    elif action_type == "mandate_save":
        link = f"/restart-autopay/{fid}"
        detail = {"link": link, "ladder": ["pause", "downgrade", "discount", "accept_churn"]}
        audit("action", f"Subscription save: calling with pause/downgrade ladder + restart link {link}",
              failure_id=fid, outcome="INFO", detail=detail)
        whatsapp.send_mandate_link(f)

    db.conn().execute("UPDATE failures SET status='recovering' WHERE id=?", (fid,))
    db.conn().commit()
    _record_action(f, action_type, "executed", detail)
    hub.broadcast({"type": "failure_update", "data": {"id": fid, "status": "recovering"}})
    return {"failure_id": fid, "action": action_type, "detail": detail}


def schedule_retry(f: dict) -> dict:
    fid = f["id"]
    if f["error_code"] == "INSUFFICIENT_FUNDS":
        when = "1st of next month (salary day)"
        brain(fid, f"Scheduling retry for {when} — timing-aware, not time-blind. Customer will be told via WhatsApp, not surprised.")
    else:
        when = "T+30 minutes"
        brain(fid, f"Transient {f['error_code']} — silent retry at {when}. Customer never knows it failed.")
    _record_action(f, "schedule_retry", "executed", {"retry_at": when})
    db.conn().execute("UPDATE failures SET status='recovering' WHERE id=?", (fid,))
    db.conn().commit()
    hub.broadcast({"type": "failure_update", "data": {"id": fid, "status": "recovering"}})
    return {"failure_id": fid, "action": "schedule_retry", "retry_at": when}


def bank_hold(f: dict) -> dict:
    fid = f["id"]
    bank = f["bank"] or "UNKNOWN"
    db.set_setting(f"bank_hold_{bank}", "1")
    audit("system", f"{bank} issuer outage detected — ALL retries for {bank} customers held until recovery",
          failure_id=fid, rule="BANK_HEALTH_HOLD", outcome="BLOCKED", detail={"bank": bank})
    brain(fid, f"Graceful failure handling: {bank} is down; hammering it now would fail 100% and burn retry budget. Waiting.")
    _record_action(f, "queue", "pending", {"bank": bank, "until": "bank recovers"})
    db.conn().execute("UPDATE failures SET status='queued' WHERE id=?", (fid,))
    db.conn().commit()
    hub.broadcast({"type": "failure_update", "data": {"id": fid, "status": "queued"}})
    hub.broadcast({"type": "bank_health", "data": {"bank": bank, "status": "down"}})
    return {"failure_id": fid, "action": "bank_hold", "bank": bank}


def release_quiet_queue() -> dict:
    """The quiet window closed — place the calls it parked.

    TRAI says defer, not drop: a call queued at 11 PM has to actually go out at
    9 AM, otherwise "queued for 09:00" is a promise the system never keeps.
    Called on a ticker, and whenever the clock or the window itself moves.
    """
    h = guardrails.current_ist_hour()
    if guardrails.in_quiet_window(h):
        return {"released": 0, "reason": "still inside quiet window"}

    parked = db.rows(
        "SELECT a.id act_id, a.action_type, f.* FROM actions a "
        "JOIN failures f ON f.id=a.failure_id "
        "WHERE a.status='pending' AND a.action_type IN ('voice_call','mandate_save') "
        "AND f.status='queued'"
    )
    if not parked:
        return {"released": 0}

    audit("system", f"Quiet window closed ({h:02d}:00 IST) — releasing {len(parked)} queued call(s)",
          rule="TRAI_QUIET_HOURS", outcome="PASSED",
          detail={"released": len(parked), "hour_ist": h, "window": guardrails.window_label()})

    results = []
    for row in parked:
        # Drop the parked row first: it stands for a call that never happened, and
        # while it exists the contact budget counts it and blocks the real one.
        db.conn().execute("DELETE FROM actions WHERE id=?", (row["act_id"],))
        db.conn().commit()
        f = {k: v for k, v in row.items() if k not in ("act_id", "action_type")}
        brain(f["id"], "Quiet hours are over — placing the call that compliance deferred, not dropped.")
        results.append(contact_customer(f, row["action_type"]))
    push_metrics()
    return {"released": len(results), "results": results}


def release_bank_hold(bank: str, send_links: bool = False) -> dict:
    """Bank is back up: release every held failure. send_links=True reaches out with a
    UPI recovery link per customer; False (batch mode) schedules silent retries."""
    db.conn().execute("DELETE FROM settings WHERE key=?", (f"bank_hold_{bank}",))
    db.conn().commit()
    held = db.rows("SELECT * FROM failures WHERE bank=? AND status='queued' AND error_code='ISSUER_DOWN'", (bank,))
    how = "sending UPI recovery links" if send_links else "scheduling silent retries"
    audit("system", f"{bank} recovered — releasing {len(held)} held failures, {how}",
          rule="BANK_HEALTH_HOLD", outcome="PASSED", detail={"bank": bank, "released": len(held)})
    hub.broadcast({"type": "bank_health", "data": {"bank": bank, "status": "up"}})
    for f in held:
        if send_links:
            contact_customer(f, "whatsapp_link")
        else:
            schedule_retry(f)
    return {"bank": bank, "released": len(held)}


def record_recovery(failure_id: str, *, discount_pct: float = 0.0, channel: str = "whatsapp",
                    is_mrr: bool = False) -> dict:
    f = db.one("SELECT * FROM failures WHERE id=?", (failure_id,))
    if not f:
        return {"error": "unknown failure"}
    if f["status"] == "recovered":
        return {"ok": True, "already": True}
    amount = int(round(f["amount"] * (1 - discount_pct / 100.0)))
    rec = {
        "id": db.new_id("rec"),
        "created_at": db.now(),
        "failure_id": failure_id,
        "amount_recovered": amount,
        "discount_pct": discount_pct,
        "channel": channel,
        "is_mrr": 1 if is_mrr else 0,
    }
    db.insert("recoveries", rec)
    db.conn().execute("UPDATE failures SET status='recovered' WHERE id=?", (failure_id,))
    db.conn().commit()
    label = "Subscription SAVED" if is_mrr else "Payment RECOVERED"
    audit("recovery", f"{label}: ₹{amount / 100:,.0f} via {channel}"
          + (f" ({discount_pct:g}% discount applied)" if discount_pct else ""),
          failure_id=failure_id, outcome="PASSED",
          detail={"amount": amount, "discount_pct": discount_pct, "channel": channel})
    hub.broadcast({"type": "failure_update", "data": {"id": failure_id, "status": "recovered"}})
    hub.broadcast({"type": "recovery", "data": rec})
    push_metrics()
    return {"ok": True, "amount_recovered": amount}


def _record_action(f: dict, action_type: str, status: str, detail: dict) -> None:
    db.insert("actions", {
        "id": db.new_id("act"),
        "created_at": db.now(),
        "failure_id": f["id"],
        "action_type": action_type,
        "channel": "voice" if action_type in ("voice_call", "mandate_save") else "whatsapp",
        "detail": db.dumps(detail),
        "status": status,
    })


def _finish_action(f: dict, action_type: str, status: str, reason: str) -> None:
    _record_action(f, action_type, status, {"blocked_reason": reason})
    if status == "blocked":
        db.conn().execute("UPDATE failures SET status='lost' WHERE id=?", (f["id"],))
        db.conn().commit()
        hub.broadcast({"type": "failure_update", "data": {"id": f["id"], "status": "lost"}})

"""Decision engine: decline-code routing, bounded LLM proposals, recovery math,
bank hold/release, and the Razorpay error-taxonomy mapping."""
from app import db, engine, llm, razorpay_gw
from conftest import make_failure


def test_decline_codes_route_per_table():
    db.set_setting("sim_hour", "14")
    expected = {
        "AUTHENTICATION_FAILED": "voice_call",
        "CARD_EXPIRED": "whatsapp_link",
        "GATEWAY_ERROR": "schedule_retry",
        "ISSUER_DOWN": "bank_hold",
        "MANDATE_CANCELLED": "mandate_save",
    }
    for i, (code, action) in enumerate(expected.items()):
        r = engine.ingest_failure(make_failure(error_code=code,
                                               customer_phone=f"+91982000000{i}"),
                                  use_llm=False)
        assert r["action"] == action, f"{code} should route to {action}, got {r['action']}"


def test_out_of_menu_llm_proposal_is_rejected(monkeypatch):
    """Bounded actions mean bounded even for the model: an off-menu proposal is
    discarded, the deterministic table decides, and the rejection is audited."""
    db.set_setting("sim_hour", "14")
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "decide", lambda f, c: {"invalid": True, "proposed": "wire_transfer"})
    r = engine.ingest_failure(make_failure(), use_llm=True)
    assert r["action"] == "voice_call"  # table's answer for AUTHENTICATION_FAILED
    rejections = db.rows("SELECT * FROM audit_log WHERE message LIKE '%REJECTED by policy validator%'")
    assert rejections


def test_llm_valid_proposal_is_used(monkeypatch):
    db.set_setting("sim_hour", "14")
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "decide", lambda f, c: {
        "root_cause": "customer", "action": "whatsapp_link",
        "reasoning": "test", "confidence": 0.9, "model": "test-model"})
    r = engine.ingest_failure(make_failure(), use_llm=True)  # table would say voice_call
    assert r["action"] == "whatsapp_link"


def test_recovery_applies_discount_and_updates_metrics():
    from app.events import metrics
    db.set_setting("sim_hour", "14")
    r = engine.ingest_failure(make_failure(amount=100000, error_code="CARD_EXPIRED"),
                              use_llm=False)
    db.set_setting(f"discount_{r['failure_id']}", "10")
    out = engine.record_recovery(r["failure_id"], discount_pct=10.0, channel="whatsapp")
    assert out["amount_recovered"] == 90000
    m = metrics()
    assert m["recovered_paise"] == 90000 and m["recovered_count"] == 1


def test_recovery_is_idempotent():
    db.set_setting("sim_hour", "14")
    r = engine.ingest_failure(make_failure(error_code="CARD_EXPIRED"), use_llm=False)
    engine.record_recovery(r["failure_id"], channel="whatsapp")
    again = engine.record_recovery(r["failure_id"], channel="whatsapp")
    assert again.get("already") is True
    assert db.one("SELECT COUNT(*) c FROM recoveries")["c"] == 1


def test_bank_hold_and_release():
    db.set_setting("sim_hour", "14")
    ids = [engine.ingest_failure(make_failure(error_code="ISSUER_DOWN", bank="ICICI",
                                              customer_phone=f"+91983000000{i}"),
                                 use_llm=False)["failure_id"] for i in range(3)]
    held = db.rows("SELECT status FROM failures WHERE id IN (?,?,?)", tuple(ids))
    assert all(h["status"] == "queued" for h in held)
    out = engine.release_bank_hold("ICICI")
    assert out["released"] == 3
    after = db.rows("SELECT status FROM failures WHERE id IN (?,?,?)", tuple(ids))
    assert all(a["status"] == "recovering" for a in after)


def test_razorpay_error_taxonomy_mapping():
    cases = {
        "authentication failed at 3ds": "AUTHENTICATION_FAILED",
        "insufficient funds in account": "INSUFFICIENT_FUNDS",
        "card is expired": "CARD_EXPIRED",
        "txn limit exceeded for the day": "TXN_LIMIT_EXCEEDED",
        "gateway timeout at acquirer": "GATEWAY_ERROR",
        "payment declined by issuer": "PAYMENT_DECLINED",
    }
    for reason, code in cases.items():
        mapped = razorpay_gw.map_failure({"error_reason": reason, "amount": 1000})
        assert mapped["error_code"] == code, f"{reason!r} -> {mapped['error_code']}"

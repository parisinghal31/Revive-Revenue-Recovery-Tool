"""The five guardrails — each one blocks exactly what it claims to block,
and every check writes an audit row (the audit trail IS the product)."""
from app import db, engine, guardrails
from conftest import make_failure


def audit_rows(rule=None):
    q = "SELECT * FROM audit_log" + (" WHERE rule=?" if rule else "")
    return db.rows(q, (rule,) if rule else ())


# ── 1. discount ceiling ──────────────────────────────────────────────────────

def test_discount_within_ceiling_passes():
    r = engine.ingest_failure(make_failure(), use_llm=False)
    assert guardrails.check_discount(r["failure_id"], 10.0).allowed


def test_discount_above_ceiling_blocked_and_audited():
    r = engine.ingest_failure(make_failure(), use_llm=False)
    res = guardrails.check_discount(r["failure_id"], 11.0)
    assert not res.allowed
    blocked = [a for a in audit_rows("MAX_DISCOUNT") if a["outcome"] == "BLOCKED"]
    assert blocked, "over-ceiling discount must write a BLOCKED audit row"


def test_discount_tool_never_writes_price_above_ceiling():
    from app import voice
    r = engine.ingest_failure(make_failure(amount=100000), use_llm=False)
    out = voice.tool_apply_discount(r["failure_id"], 20.0)
    assert out["ok"] is False
    assert db.setting(f"discount_{r['failure_id']}") is None


# ── 2. TRAI quiet hours ──────────────────────────────────────────────────────

def test_quiet_hours_queues_call_instead_of_placing_it():
    db.set_setting("sim_hour", "23")
    r = engine.ingest_failure(make_failure(), use_llm=False)  # table → voice_call
    assert r["action"] == "queued" and r["reason"] == "quiet hours"
    f = db.one("SELECT status FROM failures WHERE id=?", (r["failure_id"],))
    assert f["status"] == "queued"


def test_daytime_call_is_allowed():
    db.set_setting("sim_hour", "14")
    r = engine.ingest_failure(make_failure(), use_llm=False)
    assert r["action"] == "voice_call"


# ── 3. opt-out blacklist ─────────────────────────────────────────────────────

def test_opt_out_halts_all_future_contact():
    db.set_setting("sim_hour", "14")
    phone = "+919811111111"
    guardrails.opt_out(phone, None, "test opt-out")
    r = engine.ingest_failure(make_failure(customer_phone=phone), use_llm=False)
    assert r["action"] == "halted" and r["reason"] == "opt-out"
    f = db.one("SELECT status FROM failures WHERE id=?", (r["failure_id"],))
    assert f["status"] == "lost"


# ── 4. contact budget (no spam) ──────────────────────────────────────────────

def test_second_contact_for_same_failure_is_blocked():
    db.set_setting("sim_hour", "14")
    r = engine.ingest_failure(make_failure(), use_llm=False)
    f = db.one("SELECT * FROM failures WHERE id=?", (r["failure_id"],))
    second = engine.contact_customer(f, "whatsapp_link")
    assert second["action"] == "blocked" and second["reason"] == "contact budget"


# ── 5. fraud velocity (card-testing) ─────────────────────────────────────────

def test_fifth_rapid_failure_is_suppressed():
    db.set_setting("sim_hour", "14")
    phone = "+919900000099"
    results = [engine.ingest_failure(make_failure(customer_phone=phone,
                                                  error_code="PAYMENT_DECLINED"),
                                     use_llm=False) for _ in range(5)]
    assert results[-1]["action"] == "suppressed"
    assert all(r["action"] != "suppressed" for r in results[:4])

"""Batch simulator: the numbers the README claims must be reproducible, honest,
and include the injected adversities (outage cluster, fraud burst)."""
from app import db, simulator


def _wipe():
    for t in ["failures", "actions", "audit_log", "blacklist", "recoveries", "settings"]:
        db.conn().execute(f"DELETE FROM {t}")
    db.conn().commit()


def test_batch_is_reproducible_for_a_fixed_seed():
    r1 = simulator.run_batch(n=120, seed=7)
    _wipe()
    r2 = simulator.run_batch(n=120, seed=7)
    for key in ("at_risk_paise", "recovered_paise", "recovered_count", "yield_pct"):
        assert r1[key] == r2[key], f"{key} differs across identical seeds"


def test_batch_report_is_honest():
    r = simulator.run_batch(n=120, seed=7)
    # fraud burst suppressed, losses reported, outage held-then-released
    assert r["suppressed_fraud"]["count"] >= 1
    assert r["honest_losses"]["count"] > 0, "a batch with zero losses would be cherry-picked"
    assert r["outage_handled"]["held_then_released"] == simulator.OUTAGE_SIZE
    # recovered can never exceed at-risk
    assert r["recovered_paise"] <= r["at_risk_paise"]


def test_batch_never_sends_external_messages(monkeypatch):
    from app import whatsapp
    calls = []
    monkeypatch.setattr(whatsapp, "meta_configured", lambda: True)
    monkeypatch.setattr(whatsapp, "send_meta", lambda *a, **k: calls.append(a) or {"ok": True})
    simulator.run_batch(n=60, seed=3)
    assert calls == [], "batch records must never trigger real provider sends"

"""Guardrail layer — every check runs BEFORE an action executes and writes an audit row.

The audit trail of these checks IS the product's compliance story:
  1. TRAI quiet hours (9 PM – 9 AM IST by default, merchant-editable): outbound
     calls are queued, never placed.
  2. Opt-out blacklist: a customer who said stop is never contacted again.
  3. Discount ceiling: the agent can never authorize > MAX_DISCOUNT_PCT.
  4. Contact budget: max 1 outbound contact per failure (no spam).
  5. Fraud velocity: >= FRAUD_VELOCITY_N failures on one card/phone within
     FRAUD_WINDOW_S seconds -> recovery SUPPRESSED (card-testing pattern).
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from . import db
from .events import audit

MAX_DISCOUNT_PCT = 10.0
QUIET_START_H = 21   # 9 PM IST — regulation default, overridable per merchant
QUIET_END_H = 9      # 9 AM IST
FRAUD_VELOCITY_N = 5
FRAUD_WINDOW_S = 60
MAX_CONTACTS_PER_FAILURE = 1

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class GuardrailResult:
    allowed: bool
    rule: str
    reason: str


def current_ist_hour() -> int:
    """Demo panel can freeze the clock via the sim_hour setting."""
    override = db.setting("sim_hour")
    if override is not None:
        return int(override)
    return datetime.now(IST).hour


def quiet_window() -> tuple[int, int]:
    """The active window. Merchants can widen/narrow it from the dashboard;
    with nothing set it is the TRAI default of 9 PM - 9 AM IST."""
    start = db.setting("quiet_start_h")
    end = db.setting("quiet_end_h")
    return (int(start) if start is not None else QUIET_START_H,
            int(end) if end is not None else QUIET_END_H)


def set_quiet_window(start_h: int, end_h: int) -> tuple[int, int]:
    if not (0 <= start_h <= 23 and 0 <= end_h <= 23):
        raise ValueError("hours must be 0-23")
    db.set_setting("quiet_start_h", str(start_h))
    db.set_setting("quiet_end_h", str(end_h))
    return start_h, end_h


def in_quiet_window(h: int) -> bool:
    start, end = quiet_window()
    if start == end:
        return False                # zero-width window — quiet hours switched off
    if start < end:
        return start <= h < end     # same-day window, e.g. 01:00-05:00
    return h >= start or h < end    # wraps midnight, e.g. 21:00-09:00


def window_label() -> str:
    start, end = quiet_window()
    return f"{start:02d}:00-{end:02d}:00"


def check_quiet_hours(failure_id: str) -> GuardrailResult:
    h = current_ist_hour()
    start, end = quiet_window()
    window = window_label()
    if in_quiet_window(h):
        audit("guardrail", f"TRAI quiet hours ({h}:00 IST) — outbound call BLOCKED, queued for {end:02d}:00",
              failure_id=failure_id, rule="TRAI_QUIET_HOURS", outcome="BLOCKED",
              detail={"hour_ist": h, "window": window})
        return GuardrailResult(False, "TRAI_QUIET_HOURS", f"{h}:00 IST is inside the {window} quiet window")
    audit("guardrail", f"TRAI quiet hours check passed ({h}:00 IST, window {window})",
          failure_id=failure_id, rule="TRAI_QUIET_HOURS", outcome="PASSED",
          detail={"hour_ist": h, "window": window})
    return GuardrailResult(True, "TRAI_QUIET_HOURS", "outside quiet window")


def check_blacklist(failure_id: str, phone: str) -> GuardrailResult:
    hit = db.one("SELECT * FROM blacklist WHERE phone=?", (phone,))
    if hit:
        audit("guardrail", f"Customer {phone[-4:].rjust(10, '*')} has OPTED OUT — all contact HALTED",
              failure_id=failure_id, rule="OPT_OUT_BLACKLIST", outcome="HALTED",
              detail={"reason": hit.get("reason")})
        return GuardrailResult(False, "OPT_OUT_BLACKLIST", "customer opted out")
    audit("guardrail", "Opt-out blacklist check passed",
          failure_id=failure_id, rule="OPT_OUT_BLACKLIST", outcome="PASSED")
    return GuardrailResult(True, "OPT_OUT_BLACKLIST", "not blacklisted")


def check_discount(failure_id: str, requested_pct: float) -> GuardrailResult:
    if requested_pct > MAX_DISCOUNT_PCT:
        audit("guardrail", f"Discount {requested_pct}% exceeds {MAX_DISCOUNT_PCT}% ceiling — BLOCKED",
              failure_id=failure_id, rule="MAX_DISCOUNT", outcome="BLOCKED",
              detail={"requested": requested_pct, "ceiling": MAX_DISCOUNT_PCT})
        return GuardrailResult(False, "MAX_DISCOUNT", f"{requested_pct}% > ceiling {MAX_DISCOUNT_PCT}%")
    audit("guardrail", f"Bounded negotiation: {requested_pct}% is within {MAX_DISCOUNT_PCT}% ceiling",
          failure_id=failure_id, rule="MAX_DISCOUNT", outcome="PASSED",
          detail={"requested": requested_pct, "ceiling": MAX_DISCOUNT_PCT})
    return GuardrailResult(True, "MAX_DISCOUNT", "within ceiling")


def check_contact_budget(failure_id: str) -> GuardrailResult:
    n = db.one(
        "SELECT COUNT(*) c FROM actions WHERE failure_id=? AND action_type IN ('voice_call','whatsapp_link') AND status!='blocked'",
        (failure_id,),
    )["c"]
    if n >= MAX_CONTACTS_PER_FAILURE:
        audit("guardrail", f"Contact budget exhausted ({n}/{MAX_CONTACTS_PER_FAILURE}) — no re-contact",
              failure_id=failure_id, rule="CONTACT_BUDGET", outcome="BLOCKED", detail={"used": n})
        return GuardrailResult(False, "CONTACT_BUDGET", "already contacted for this failure")
    audit("guardrail", "Contact budget check passed (0 prior contacts)",
          failure_id=failure_id, rule="CONTACT_BUDGET", outcome="PASSED")
    return GuardrailResult(True, "CONTACT_BUDGET", "budget available")


def check_fraud_velocity(failure_id: str, phone: str) -> GuardrailResult:
    since = db.now() - FRAUD_WINDOW_S
    n = db.one(
        "SELECT COUNT(*) c FROM failures WHERE customer_phone=? AND created_at>=?",
        (phone, since),
    )["c"]
    if n >= FRAUD_VELOCITY_N:
        audit("guardrail",
              f"POSSIBLE CARD-TESTING ATTACK: {n} failures in {FRAUD_WINDOW_S}s from same source — recovery SUPPRESSED",
              failure_id=failure_id, rule="FRAUD_VELOCITY", outcome="BLOCKED",
              detail={"failures_in_window": n, "window_s": FRAUD_WINDOW_S})
        return GuardrailResult(False, "FRAUD_VELOCITY", "velocity anomaly — do not chase this money")
    audit("guardrail", f"Fraud velocity check passed ({n} in last {FRAUD_WINDOW_S}s)",
          failure_id=failure_id, rule="FRAUD_VELOCITY", outcome="PASSED",
          detail={"failures_in_window": n})
    return GuardrailResult(True, "FRAUD_VELOCITY", "normal velocity")


def opt_out(phone: str, failure_id: str | None = None, reason: str = "customer said stop") -> None:
    db.insert("blacklist", {"phone": phone, "created_at": db.now(), "reason": reason})
    audit("guardrail", f"OPT-OUT registered for {phone[-4:].rjust(10, '*')} — {reason}. All future contact HALTED.",
          failure_id=failure_id, rule="OPT_OUT_BLACKLIST", outcome="HALTED", detail={"reason": reason})

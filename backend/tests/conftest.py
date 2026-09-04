"""Test fixtures: every test runs against an isolated throwaway SQLite file,
with no LLM keys (deterministic policy-table path) and no external providers.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# isolated DB + clean env BEFORE the app modules import
_tmp = tempfile.mkdtemp(prefix="revive-test-")
os.environ["REVIVE_DB_PATH"] = str(Path(_tmp) / "test.db")
for var in ("GROQ_API_KEY", "GEMINI_API_KEY", "TWILIO_SID", "TWILIO_TOKEN",
            "CALLMEBOT_PHONE", "CALLMEBOT_APIKEY", "META_WA_TOKEN", "META_WA_PHONE_ID",
            "TEXTMEBOT_PHONE", "TEXTMEBOT_APIKEY", "GREEN_ID", "GREEN_TOKEN",
            "VAPI_SIP_NUMBER_ID", "CUSTOMER_SIP_URI", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET"):
    os.environ.pop(var, None)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    """Empty every table before each test — same wipe the sandbox reset uses."""
    for t in ["failures", "actions", "audit_log", "blacklist", "recoveries", "settings"]:
        db.conn().execute(f"DELETE FROM {t}")
    db.conn().commit()
    yield


def make_failure(**overrides):
    payload = {
        "customer_name": "Test", "customer_phone": "+919800000001",
        "amount": 49900, "method": "card",
        "error_code": "AUTHENTICATION_FAILED", "bank": "HDFC",
    }
    payload.update(overrides)
    return payload

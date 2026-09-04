"""Health-probe tests — the first HTTP-level coverage in the suite.

The hosting platform (Render/Fly/K8s) decides whether to route traffic based on
/health, so a regression here silently takes the whole service offline.
"""
from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_ok_with_a_reachable_database():
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_health_never_leaks_credential_values():
    """Configured-ness is public; the values are not. This endpoint is unauthenticated,
    so it must expose booleans only — never a key, even a truncated one."""
    with TestClient(app) as client:
        body = client.get("/health").json()
    integrations = body["integrations"]
    assert integrations, "expected the integration roster to be reported"
    for name, value in integrations.items():
        assert isinstance(value, bool), f"{name} must be a bool, got {type(value).__name__}"

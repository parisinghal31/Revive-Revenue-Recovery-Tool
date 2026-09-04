"""WebSocket broadcast hub — every audit row and metric change is pushed live to the dashboard."""
import asyncio
import json
from typing import Any

from . import db


class Hub:
    def __init__(self) -> None:
        self.clients: set[Any] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def register_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def connect(self, ws) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws) -> None:
        self.clients.discard(ws)

    async def _send_all(self, payload: str) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def broadcast(self, event: dict) -> None:
        """Thread-safe fire-and-forget broadcast (callable from sync code)."""
        payload = json.dumps(event, ensure_ascii=False)
        if self.loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._send_all(payload), self.loop)


hub = Hub()


def audit(category: str, message: str, *, failure_id: str | None = None,
          rule: str | None = None, outcome: str = "INFO", detail: dict | None = None) -> dict:
    """Write an audit row AND push it to the dashboard in one call."""
    row = {
        "id": db.new_id("aud"),
        "created_at": db.now(),
        "failure_id": failure_id,
        "category": category,
        "rule": rule,
        "outcome": outcome,
        "message": message,
        "detail": db.dumps(detail or {}),
    }
    db.insert("audit_log", row)
    hub.broadcast({"type": "audit", "data": row})
    return row


def metrics() -> dict:
    rec = db.one("SELECT COALESCE(SUM(amount_recovered),0) s, COUNT(*) c FROM recoveries WHERE is_mrr=0") or {}
    mrr = db.one("SELECT COALESCE(SUM(amount_recovered),0) s, COUNT(*) c FROM recoveries WHERE is_mrr=1") or {}
    fails = db.one("SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM failures WHERE kind='payment_failed'") or {}
    recovered_count = rec.get("c", 0)
    total_fail = fails.get("c", 0) or 1
    return {
        "recovered_paise": rec.get("s", 0),
        "recovered_count": recovered_count,
        "mrr_saved_paise": mrr.get("s", 0),
        "mrr_saved_count": mrr.get("c", 0),
        "failures_count": fails.get("c", 0),
        "at_risk_paise": fails.get("s", 0),
        "yield_pct": round(100.0 * recovered_count / total_fail, 1),
    }


def push_metrics() -> None:
    hub.broadcast({"type": "metrics", "data": metrics()})

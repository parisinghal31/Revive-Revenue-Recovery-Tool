"""SQLite persistence layer for Revive. Single-file DB, zero external services.

REVIVE_DB_PATH overrides the location (tests and the reproducible demo run use
an isolated file so results never mix with interactive state).
"""
import os
import sqlite3
import json
import time
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path(os.environ.get("REVIVE_DB_PATH")
               or Path(__file__).resolve().parent.parent / "revive.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS failures (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    order_id TEXT,
    customer_name TEXT,
    customer_phone TEXT,
    amount INTEGER NOT NULL,           -- paise
    method TEXT,                       -- card | upi | netbanking
    error_code TEXT NOT NULL,          -- Razorpay-style decline code
    error_source TEXT,                 -- bank | customer | gateway
    bank TEXT,
    kind TEXT NOT NULL DEFAULT 'payment_failed',  -- payment_failed | subscription_cancelled | checkout_abandoned
    status TEXT NOT NULL DEFAULT 'open'           -- open | recovering | recovered | lost | suppressed | queued
);

CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    failure_id TEXT NOT NULL,
    action_type TEXT NOT NULL,         -- voice_call | whatsapp_link | schedule_retry | suppress | queue | halt
    channel TEXT,
    detail TEXT,                       -- JSON
    status TEXT NOT NULL DEFAULT 'pending'  -- pending | executed | blocked | done
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    failure_id TEXT,
    category TEXT NOT NULL,            -- decision | guardrail | action | recovery | system | brain
    rule TEXT,
    outcome TEXT,                      -- PASSED | BLOCKED | HALTED | INFO
    message TEXT NOT NULL,
    detail TEXT                        -- JSON
);

CREATE TABLE IF NOT EXISTS blacklist (
    phone TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS recoveries (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    failure_id TEXT NOT NULL,
    amount_recovered INTEGER NOT NULL, -- paise, post-discount
    discount_pct REAL NOT NULL DEFAULT 0,
    channel TEXT,                      -- voice | whatsapp | retry | mandate_restart
    is_mrr INTEGER NOT NULL DEFAULT 0  -- 1 when a subscription was saved
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


_conn = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now() -> float:
    return time.time()


def insert(table: str, row: dict[str, Any]) -> None:
    keys = ",".join(row.keys())
    marks = ",".join("?" for _ in row)
    conn().execute(f"INSERT OR REPLACE INTO {table} ({keys}) VALUES ({marks})", list(row.values()))
    conn().commit()


def rows(sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql: str, args: tuple = ()) -> dict | None:
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def setting(key: str, default: str | None = None) -> str | None:
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default


def set_setting(key: str, value: str) -> None:
    insert("settings", {"key": key, "value": value})


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)

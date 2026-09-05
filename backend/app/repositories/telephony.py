# -*- coding: utf-8 -*-
"""通话事件仓库：运营商/呼叫中心回调事件的持久化与状态查询。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import get_settings

_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS call_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    event TEXT NOT NULL,
    caller TEXT DEFAULT '',
    recording_url TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'received',
    -- received → processing → done | failed
    case_id TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_call_events_call ON call_events(call_id);
"""


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        settings = get_settings()
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(settings.sqlite_path), check_same_thread=False, timeout=30)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")  # 读写不互斥，后台长任务与回调并发不撞锁
        _conn.executescript(_SCHEMA)
        _conn.commit()
    return _conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_event(call_id: str, provider: str, event: str, caller: str, recording_url: str) -> int:
    db = _db()
    cur = db.execute(
        "INSERT INTO call_events (call_id, provider, event, caller, recording_url, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'received', ?, ?)",
        (call_id, provider, event, caller, recording_url, _now(), _now()),
    )
    db.commit()
    return int(cur.lastrowid)


def update_status(call_id: str, status: str, *, case_id: str = "", detail: str = "") -> None:
    db = _db()
    db.execute(
        "UPDATE call_events SET status = ?, case_id = CASE WHEN ? != '' THEN ? ELSE case_id END, "
        "detail = CASE WHEN ? != '' THEN ? ELSE detail END, updated_at = ? WHERE call_id = ?",
        (status, case_id, case_id, detail, detail, _now(), call_id),
    )
    db.commit()


def latest_by_call(call_id: str) -> Optional[dict]:
    row = _db().execute(
        "SELECT * FROM call_events WHERE call_id = ? ORDER BY id DESC LIMIT 1", (call_id,)
    ).fetchone()
    return dict(row) if row else None


def list_recent(limit: int = 20) -> list[dict]:
    rows = _db().execute(
        "SELECT * FROM call_events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]

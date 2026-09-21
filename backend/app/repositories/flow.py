# -*- coding: utf-8 -*-
"""工单流转仓库：flow_state 列迁移 + 流转日志 + 看板查询。

- flow_state 通过幂等 ALTER TABLE 加到既有 cases 表（默认 'received'），既有数据零迁移成本；
- 每次迁移写入 case_flow_log（谁、何时、从哪到哪、依据）；
- 看板按流转状态分组返回，附带时限状态（临期/超期）便于督办。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.core.config import get_settings
from app.services import workflow_state

_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS case_flow_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    actor TEXT,
    role TEXT,
    action TEXT,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_flow_log_case ON case_flow_log(case_id);
"""


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        settings = get_settings()
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(settings.sqlite_path), check_same_thread=False, timeout=30)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(_SCHEMA)
        cols = {r[1] for r in _conn.execute("PRAGMA table_info(cases)").fetchall()}
        if "flow_state" not in cols:
            _conn.execute("ALTER TABLE cases ADD COLUMN flow_state TEXT DEFAULT 'received'")
        _conn.commit()
    return _conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_state(case_id: str) -> Optional[str]:
    row = _db().execute("SELECT flow_state FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    if row is None:
        return None
    return row[0] or "received"


def log(case_id: str, from_state: str | None, to_state: str, actor: str, role: str, action: str, note: str = "") -> None:
    _db().execute(
        """INSERT INTO case_flow_log (case_id, from_state, to_state, actor, role, action, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (case_id, from_state, to_state, actor, role, action, note, _now()),
    )
    _db().commit()


def set_state(case_id: str, to_state: str, actor: str = "system", role: str = "system",
              action: str = "", note: str = "", expected_from: str | None = None) -> tuple[bool, str]:
    """带守卫的状态写入：expected_from 非空时做乐观并发校验。"""
    db = _db()
    current = get_state(case_id)
    if current is None:
        return False, "案件不存在"
    if expected_from is not None and current != expected_from:
        return False, f"状态已变化（当前：{workflow_state.label(current)}），请刷新后重试"
    db.execute("UPDATE cases SET flow_state = ?, updated_at = ? WHERE case_id = ?", (to_state, _now(), case_id))
    db.commit()
    log(case_id, current, to_state, actor, role, action or workflow_state.label(to_state), note)
    return True, ""


def history(case_id: str) -> list[dict]:
    rows = _db().execute(
        "SELECT * FROM case_flow_log WHERE case_id = ? ORDER BY id", (case_id,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["from_label"] = workflow_state.label(d["from_state"]) if d["from_state"] else ""
        d["to_label"] = workflow_state.label(d["to_state"])
        out.append(d)
    return out


def counts() -> dict[str, int]:
    rows = _db().execute(
        "SELECT COALESCE(flow_state, 'received') AS s, COUNT(*) AS n FROM cases GROUP BY s"
    ).fetchall()
    return {r["s"]: r["n"] for r in rows}


def cases_by_state(state: str, limit: int = 50) -> list[dict]:
    rows = _db().execute(
        """SELECT case_id, raw_text, status, flow_state, created_at, updated_at, work_order, assessment
           FROM cases WHERE COALESCE(flow_state, 'received') = ?
           ORDER BY updated_at DESC LIMIT ?""",
        (state, limit),
    ).fetchall()
    import json

    out = []
    for r in rows:
        d = dict(r)
        wo = json.loads(d.pop("work_order")) if d.get("work_order") else {}
        assessment = json.loads(d.pop("assessment")) if d.get("assessment") else {}
        out.append({
            "case_id": d["case_id"],
            "title": (wo or {}).get("title") or (d.get("raw_text") or "")[:30],
            "status": d["status"],
            "flow_state": d["flow_state"] or "received",
            "flow_label": workflow_state.label(d["flow_state"] or "received"),
            "urgency_level": ((assessment or {}).get("urgency") or {}).get("level", "一般"),
            "created_at": d["created_at"],
            "updated_at": d["updated_at"],
        })
    return out

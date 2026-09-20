"""案件仓库：SQLite 持久化（aiohttp 风格的同步 API，FastAPI 同步端点使用）。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.config import get_settings

_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    source_channel TEXT NOT NULL,
    status TEXT NOT NULL,
    understanding TEXT,
    work_order TEXT,
    classification TEXT,
    routing TEXT,
    reply_draft TEXT,
    review TEXT NOT NULL DEFAULT '{"work_order":"pending","classification":"pending","routing":"pending","reply":"pending"}',
    review_note TEXT DEFAULT '',
    clarification_context TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    error TEXT
);
"""


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        settings = get_settings()
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        path: Path = settings.sqlite_path
        _conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")  # 读写不互斥，并发场景防 database is locked
        _conn.execute(_SCHEMA)
        _migrate(_conn)
        _conn.commit()
    return _conn


def _migrate(db: sqlite3.Connection) -> None:
    """幂等迁移：为既有库补新增列（assessment 存急件分级等评估结论）。"""
    cols = {r[1] for r in db.execute("PRAGMA table_info(cases)").fetchall()}
    if "assessment" not in cols:
        db.execute("ALTER TABLE cases ADD COLUMN assessment TEXT")
        db.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("understanding", "work_order", "classification", "routing", "reply_draft", "assessment"):
        d[key] = json.loads(d[key]) if d.get(key) else None
    d["review"] = json.loads(d["review"]) if d["review"] else {}
    d["clarification_context"] = json.loads(d["clarification_context"]) or []
    return d


def create_case(
    case_id: str,
    thread_id: str,
    raw_text: str,
    source_channel: str,
    status: str,
) -> None:
    db = _db()
    db.execute(
        """INSERT INTO cases (case_id, thread_id, raw_text, source_channel, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (case_id, thread_id, raw_text, source_channel, status, _now(), _now()),
    )
    db.commit()


def save_state(
    case_id: str,
    *,
    status: str,
    thread_id: str | None = None,
    understanding: Optional[dict] = None,
    work_order: Optional[dict] = None,
    classification: Optional[dict] = None,
    routing: Optional[dict] = None,
    reply_draft: Optional[dict] = None,
    assessment: Optional[dict] = None,
    clarification_context: Optional[list[str]] = None,
    error: Optional[str] = None,
    completed: bool = False,
) -> None:
    db = _db()
    sets = ["updated_at = ?"]
    params: list[Any] = [_now()]
    if thread_id is not None:
        sets.append("thread_id = ?")
        params.append(thread_id)
    if understanding is not None:
        sets.append("understanding = ?")
        params.append(json.dumps(understanding, ensure_ascii=False))
    if work_order is not None:
        sets.append("work_order = ?")
        params.append(json.dumps(work_order, ensure_ascii=False))
    if classification is not None:
        sets.append("classification = ?")
        params.append(json.dumps(classification, ensure_ascii=False))
    if routing is not None:
        sets.append("routing = ?")
        params.append(json.dumps(routing, ensure_ascii=False))
    if reply_draft is not None:
        sets.append("reply_draft = ?")
        params.append(json.dumps(reply_draft, ensure_ascii=False))
    if assessment is not None:
        sets.append("assessment = ?")
        params.append(json.dumps(assessment, ensure_ascii=False))
    if clarification_context is not None:
        sets.append("clarification_context = ?")
        params.append(json.dumps(clarification_context, ensure_ascii=False))
    sets.append("status = ?")
    params.append(status)
    if error is not None:
        sets.append("error = ?")
        params.append(error)
    if completed:
        sets.append("completed_at = ?")
        params.append(_now())
    params.append(case_id)
    db.execute(f"UPDATE cases SET {', '.join(sets)} WHERE case_id = ?", params)
    db.commit()


def get_case(case_id: str) -> Optional[dict]:
    row = _db().execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_cases(limit: int = 50) -> list[dict]:
    rows = _db().execute(
        "SELECT * FROM cases ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_section(case_id: str, column: str, value: dict, review_key: str | None = None) -> None:
    """工作人员修改某一节内容（approve 时不覆盖）。column 为数据库列名，review_key 为审核状态键名。"""
    db = _db()
    key = review_key or column
    db.execute(
        f"UPDATE cases SET {column} = ?, updated_at = ? WHERE case_id = ?",
        (json.dumps(value, ensure_ascii=False), _now(), case_id),
    )
    db.execute(
        "UPDATE cases SET review = json_set(review, '$." + key + "', ?), updated_at = ? WHERE case_id = ?",
        ("modified", _now(), case_id),
    )
    db.commit()


def approve_section(case_id: str, section: str, note: str = "") -> None:
    db = _db()
    db.execute(
        "UPDATE cases SET review = json_set(review, '$." + section + "', 'approved'), review_note = ?, updated_at = ? WHERE case_id = ?",
        (note, _now(), case_id),
    )
    db.commit()


def set_completed(case_id: str) -> None:
    db = _db()
    db.execute(
        "UPDATE cases SET status = 'completed', completed_at = ?, updated_at = ? WHERE case_id = ?",
        (_now(), _now(), case_id),
    )
    db.commit()


def append_clarification(case_id: str, answer: str, new_thread_id: str) -> list[str]:
    db = _db()
    case = get_case(case_id)
    ctx = list(case["clarification_context"]) if case else []
    ctx.append(answer)
    db.execute(
        "UPDATE cases SET clarification_context = ?, thread_id = ?, status = 'processing', updated_at = ? WHERE case_id = ?",
        (json.dumps(ctx, ensure_ascii=False), new_thread_id, _now(), case_id),
    )
    db.commit()
    return ctx

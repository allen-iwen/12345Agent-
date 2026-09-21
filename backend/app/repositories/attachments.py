# -*- coding: utf-8 -*-
"""图片/音频证据附件仓库（SQLite）。

案件受理时可携带现场照片等证据；图片经视觉模型分析后，结论作为依据链的一部分
影响事项分类与急件分级。附件在入库前会先进入暂存态（case_id 为空），
建单时通过 attachment_ids 关联到案件。
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import get_settings

_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS case_attachments (
    id TEXT PRIMARY KEY,
    case_id TEXT,
    kind TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    mime TEXT,
    size INTEGER,
    sha256 TEXT,
    vision_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attachments_case ON case_attachments(case_id);
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
        _conn.commit()
    return _conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(row: sqlite3.Row | None) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row)
    d["vision"] = json.loads(d.pop("vision_json")) if d.get("vision_json") else None
    return d


def create(
    kind: str,
    filename: str,
    path: str,
    mime: str,
    size: int,
    sha256: str,
    vision: dict | None = None,
) -> dict:
    aid = uuid.uuid4().hex[:12]
    _db().execute(
        """INSERT INTO case_attachments (id, case_id, kind, filename, path, mime, size, sha256, vision_json, created_at)
           VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (aid, kind, filename, path, mime, size, sha256,
         json.dumps(vision, ensure_ascii=False) if vision else None, _now()),
    )
    _db().commit()
    return {"id": aid}


def set_vision(attachment_id: str, vision: dict) -> None:
    db = _db()
    db.execute("UPDATE case_attachments SET vision_json = ? WHERE id = ?",
               (json.dumps(vision, ensure_ascii=False), attachment_id))
    db.commit()


def link_to_case(attachment_ids: list[str], case_id: str) -> int:
    if not attachment_ids:
        return 0
    db = _db()
    n = 0
    for aid in attachment_ids:
        cur = db.execute("UPDATE case_attachments SET case_id = ? WHERE id = ? AND case_id IS NULL", (case_id, aid))
        n += cur.rowcount or 0
    db.commit()
    return n


def get(attachment_id: str) -> Optional[dict]:
    return _row(_db().execute("SELECT * FROM case_attachments WHERE id = ?", (attachment_id,)).fetchone())


def list_by_case(case_id: str) -> list[dict]:
    rows = _db().execute(
        "SELECT * FROM case_attachments WHERE case_id = ? ORDER BY created_at", (case_id,)
    ).fetchall()
    return [_row(r) for r in rows]


def list_pending(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = _db().execute(
        f"SELECT * FROM case_attachments WHERE id IN ({marks}) AND case_id IS NULL", ids
    ).fetchall()
    return [_row(r) for r in rows]


def delete(attachment_id: str) -> Optional[dict]:
    row = get(attachment_id)
    if row is None:
        return None
    _db().execute("DELETE FROM case_attachments WHERE id = ?", (attachment_id,))
    _db().commit()
    try:
        Path(row["path"]).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 - 文件删除失败不影响记录清理
        pass
    return row

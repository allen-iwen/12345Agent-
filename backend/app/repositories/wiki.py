# -*- coding: utf-8 -*-
"""知识词条（wiki）仓库：词条 + 版本历史。

定位（与既有知识资产的分工）：
- 政策库 / 部门职责 / 12 类目录 = **依据层**（决定判断的事实来源，只读或由管理端维护）；
- wiki 词条 = **口径层**（人可维护的办理经验、答话口径、案例复盘、政策解读），
  支持草稿→发布、逐次修订留版本，答复草拟时可选择性引用已发布口径。

全部幂等建表；搜索用 SQLite LIKE（数据量小，无需引入全文索引）。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.core.config import get_settings

_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wiki_entries (
    slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '办事指南',
    body_md TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    author TEXT DEFAULT '',
    reviewer TEXT DEFAULT '',
    source_case_id TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wiki_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    body_md TEXT NOT NULL,
    editor TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wiki_rev ON wiki_revisions(slug, version);
"""

CATEGORIES = ("政策解读", "部门职责", "办事指南", "案例经验", "口径话术")


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
    try:
        d["tags"] = json.loads(d.get("tags") or "[]")
    except json.JSONDecodeError:
        d["tags"] = []
    return d


def upsert(slug: str, title: str, body_md: str, category: str = "办事指南",
           tags: list[str] | None = None, author: str = "", note: str = "",
           source_case_id: str = "") -> dict:
    """新建或更新词条（更新即 +1 版本并写入修订历史）。"""
    db = _db()
    existing = _row(db.execute("SELECT * FROM wiki_entries WHERE slug = ?", (slug,)).fetchone())
    tags_json = json.dumps(tags or [], ensure_ascii=False)
    if existing is None:
        db.execute(
            """INSERT INTO wiki_entries (slug, title, category, body_md, tags, version, status, author, source_case_id, created_at, updated_at)
               VALUES (?,?,?,?,?,1,'draft',?,?,?,?)""",
            (slug, title, category, body_md, tags_json, author, source_case_id, _now(), _now()),
        )
        version = 1
    else:
        version = int(existing["version"]) + 1
        db.execute(
            """UPDATE wiki_entries SET title=?, category=?, body_md=?, tags=?, version=?, author=?, updated_at=?
               WHERE slug=?""",
            (title, category, body_md, tags_json, version, author, _now(), slug),
        )
    db.execute(
        "INSERT INTO wiki_revisions (slug, version, title, body_md, editor, note, created_at) VALUES (?,?,?,?,?,?,?)",
        (slug, version, title, body_md, author, note, _now()),
    )
    db.commit()
    return {"slug": slug, "version": version, "status": existing["status"] if existing else "draft"}


def publish(slug: str, reviewer: str = "") -> bool:
    db = _db()
    cur = db.execute("UPDATE wiki_entries SET status='published', reviewer=?, updated_at=? WHERE slug=?",
                     (reviewer, _now(), slug))
    db.commit()
    return bool(cur.rowcount)


def revise_status(slug: str, status: str, reviewer: str = "") -> bool:
    db = _db()
    cur = db.execute("UPDATE wiki_entries SET status=?, reviewer=?, updated_at=? WHERE slug=?",
                     (status, reviewer, _now(), slug))
    db.commit()
    return bool(cur.rowcount)


def get(slug: str) -> Optional[dict]:
    return _row(_db().execute("SELECT * FROM wiki_entries WHERE slug = ?", (slug,)).fetchone())


def list_entries(category: str | None = None, status: str | None = None, q: str | None = None,
                 limit: int = 100) -> list[dict]:
    sql = "SELECT * FROM wiki_entries"
    where, params = [], []
    if category:
        where.append("category = ?")
        params.append(category)
    if status:
        where.append("status = ?")
        params.append(status)
    if q:
        where.append("(title LIKE ? OR body_md LIKE ? OR tags LIKE ?)")
        params += [f"%{q}%"] * 3
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    return [_row(r) for r in _db().execute(sql, params).fetchall()]


def revisions(slug: str) -> list[dict]:
    rows = _db().execute(
        "SELECT id, slug, version, title, editor, note, created_at FROM wiki_revisions WHERE slug = ? ORDER BY version DESC",
        (slug,),
    ).fetchall()
    return [dict(r) for r in rows]


def revision_body(slug: str, version: int) -> Optional[dict]:
    row = _db().execute("SELECT * FROM wiki_revisions WHERE slug = ? AND version = ?", (slug, version)).fetchone()
    return dict(row) if row else None


def delete(slug: str) -> bool:
    db = _db()
    cur = db.execute("DELETE FROM wiki_entries WHERE slug = ?", (slug,))
    db.execute("DELETE FROM wiki_revisions WHERE slug = ?", (slug,))
    db.commit()
    return bool(cur.rowcount)


def counts() -> dict:
    rows = _db().execute("SELECT status, COUNT(*) AS n FROM wiki_entries GROUP BY status").fetchall()
    by_cat = _db().execute("SELECT category, COUNT(*) AS n FROM wiki_entries GROUP BY category").fetchall()
    return {
        "by_status": {r["status"]: r["n"] for r in rows},
        "by_category": {r["category"]: r["n"] for r in by_cat},
        "total": sum(r["n"] for r in rows),
    }

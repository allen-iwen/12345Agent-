# -*- coding: utf-8 -*-
"""轻量 RBAC 与审计仓库：用户 / 会话 / 操作审计。

设计取舍（轻量但不含糊）：
- 只做「谁是谁 + 能做什么 + 做了什么」，不做 OAuth/组织架构同步；
- 密码用 pbkdf2_hmac-SHA256 + 随机盐，绝不明文；会话是有过期时间的随机 token；
- 审计日志不可修改（只插入），记录操作者、角色、动作、对象与依据，满足「谁审的、谁改的」可追责；
- 全部表用幂等建表，既有库零迁移成本。
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import get_settings

_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'agent',
    org TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT DEFAULT '',
    target_id TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_log(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
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


# ---------------- 用户 ----------------


def create_user(username: str, display_name: str, password_hash: str, role: str, org: str = "") -> int:
    cur = _db().execute(
        "INSERT INTO users (username, display_name, password_hash, role, org, active, created_at) VALUES (?,?,?,?,?,1,?)",
        (username, display_name, password_hash, role, org, _now()),
    )
    _db().commit()
    return int(cur.lastrowid or 0)


def get_user(username: str) -> Optional[dict]:
    row = _db().execute("SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    row = _db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_users() -> list[dict]:
    rows = _db().execute(
        "SELECT id, username, display_name, role, org, active, created_at FROM users ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def count_users() -> int:
    return int(_db().execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])


# ---------------- 会话 ----------------


def create_session(user_id: int, ttl_hours: int) -> dict:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat(timespec="seconds")
    _db().execute(
        "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?,?,?,?)",
        (token, user_id, expires, _now()),
    )
    _db().commit()
    return {"token": token, "expires_at": expires}


def resolve_session(token: str) -> Optional[dict]:
    if not token:
        return None
    row = _db().execute("SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
    if row is None:
        return None
    if row["expires_at"] < _now():
        _db().execute("DELETE FROM sessions WHERE token = ?", (token,))
        _db().commit()
        return None
    user = get_user_by_id(int(row["user_id"]))
    if user is None or not user.get("active"):
        return None
    return {
        "user_id": user["id"],
        "username": user["username"],
        "actor": user["display_name"] or user["username"],
        "role": user["role"],
        "org": user.get("org") or "",
        "expires_at": row["expires_at"],
    }


def delete_session(token: str) -> None:
    _db().execute("DELETE FROM sessions WHERE token = ?", (token,))
    _db().commit()


# ---------------- 审计 ----------------


def add_audit(actor: str, role: str, action: str, target_type: str = "", target_id: str = "",
              detail: dict | str | None = None, ip: str = "") -> None:
    if isinstance(detail, dict):
        detail = json.dumps(detail, ensure_ascii=False)
    _db().execute(
        "INSERT INTO audit_log (actor, role, action, target_type, target_id, detail, ip, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (actor or "unknown", role or "", action, target_type, target_id, detail or "", ip, _now()),
    )
    _db().commit()


def list_audit(limit: int = 100, target_id: str | None = None, actor: str | None = None) -> list[dict]:
    sql = "SELECT * FROM audit_log"
    where, params = [], []
    if target_id:
        where.append("target_id = ?")
        params.append(target_id)
    if actor:
        where.append("actor = ?")
        params.append(actor)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in _db().execute(sql, params).fetchall()]


def count_audit() -> int:
    return int(_db().execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"])

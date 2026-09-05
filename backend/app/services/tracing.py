"""Trace 持久化：每次 Agent 节点的输入/输出/耗时/提示词摘要记录到 SQLite，供前端抽屉展示。"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    node TEXT NOT NULL,
    prompt_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT,
    duration_ms INTEGER,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_case ON runs(case_id);
"""


def init(storage_dir: Path) -> None:
    """惰性初始化连接。"""
    global _conn
    if _conn is not None:
        return
    storage_dir.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(storage_dir / "runs.sqlite3"), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(_SCHEMA)
    _conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def record_start(case_id: str, node: str, prompt_kind: str, input_payload: Any) -> int:
    """记录节点开始（返回 run id，供 record_end 用）。"""
    if _conn is None:
        raise RuntimeError("runs store 未初始化")
    with _lock:
        cur = _conn.execute(
            "INSERT INTO runs (case_id, node, prompt_kind, status, input_json, created_at) VALUES (?, ?, ?, 'running', ?, ?)",
            (case_id, node, prompt_kind, json.dumps(input_payload, ensure_ascii=False, default=str), _now()),
        )
        _conn.commit()
        return int(cur.lastrowid)


def record_end(run_id: int, output: Any | None, error: str | None = None, duration_ms: int | None = None) -> None:
    if _conn is None:
        return
    with _lock:
        if error:
            _conn.execute(
                "UPDATE runs SET status='failed', output_json=?, error=?, duration_ms=? WHERE id=?",
                (json.dumps({"_error": error}, ensure_ascii=False), error, duration_ms, run_id),
            )
        else:
            _conn.execute(
                "UPDATE runs SET status='ok', output_json=?, duration_ms=? WHERE id=?",
                (json.dumps(output, ensure_ascii=False, default=str) if output is not None else None, duration_ms, run_id),
            )
        _conn.commit()


def sum_case_ms(case_id: str) -> int:
    """单案智能体节点累计耗时（毫秒）。"""
    if _conn is None:
        return 0
    row = _conn.execute(
        "SELECT COALESCE(SUM(duration_ms), 0) AS total FROM runs WHERE case_id = ? AND duration_ms IS NOT NULL",
        (case_id,),
    ).fetchone()
    return int(row["total"] or 0) if row else 0


def totals() -> dict:
    """全局效率账本：总节点耗时、案件数（去重）。"""
    if _conn is None:
        return {"agent_ms_total": 0, "cases_traced": 0}
    row = _conn.execute(
        "SELECT COALESCE(SUM(duration_ms), 0) AS total, COUNT(DISTINCT case_id) AS n FROM runs WHERE duration_ms IS NOT NULL"
    ).fetchone()
    return {"agent_ms_total": int(row["total"] or 0), "cases_traced": int(row["n"] or 0)}


def list_runs(case_id: str) -> list[dict]:
    if _conn is None:
        return []
    rows = _conn.execute(
        "SELECT id, node, prompt_kind, status, input_json, output_json, duration_ms, error, created_at FROM runs WHERE case_id = ? ORDER BY id",
        (case_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["input_json"] = json.loads(d["input_json"]) if d["input_json"] else None
        except Exception:
            pass
        try:
            d["output_json"] = json.loads(d["output_json"]) if d["output_json"] else None
        except Exception:
            pass
        out.append(d)
    return out


def get_run(run_id: int) -> dict | None:
    if _conn is None:
        return None
    row = _conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    for k in ("input_json", "output_json"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
    return d
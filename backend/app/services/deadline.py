# -*- coding: utf-8 -*-
"""支柱五：办理时限倒计时与超期督办。

依据《安徽省12345热线诉求闭环办理工作规范》：
- 紧急事项（大面积停水停电、环境污染等）第一时间处置 + 24 小时内反馈进展；
- 一般性诉求在规定时限内办结，可申请延期或「承诺办理」（复杂事项不超过 9 个月）。

设计原则（诚实优先）：
- 等级时限来自规范条款；**一般件工作日数未公开细则核对的，在输出中标注为「建议值」**；
- 法定节假日数据缺失时，仅按周末计算工作日，并在输出中显式标注，不凭空填写日期；
- 输出到期时刻、剩余时长与「正常/临期/超期」状态，供看板与督办使用。
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def _rules() -> dict:
    path = get_settings().data_dir / "dispatch" / "deadline_rules.json"
    if not path.exists():
        logger.warning("deadline_rules.json 缺失，时限计算降级")
        return {"levels": {}, "legal_basis": {}}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def _holidays() -> tuple[frozenset[date], frozenset[date], bool]:
    """返回（法定节假日, 调休工作日, 是否已配置）。"""
    path = get_settings().holidays_path
    if not path.exists():
        return frozenset(), frozenset(), False

    def _parse(items: list[str]) -> frozenset[date]:
        out = set()
        for s in items or []:
            try:
                out.add(date.fromisoformat(str(s)))
            except ValueError:
                logger.warning("holidays.json 日期格式无法解析：%s", s)
        return frozenset(out)

    data = json.loads(path.read_text(encoding="utf-8"))
    holidays = _parse(data.get("holidays", []))
    extra = _parse(data.get("extra_workdays", []))
    return holidays, extra, bool(holidays or extra)


def _parse_dt(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.now()


def _add_workdays(start: datetime, days: int, holidays: frozenset[date], extra: frozenset[date]) -> datetime:
    """按工作日推进：跳过周末与法定节假日，把调休工作日计为工作日。"""
    cur = start
    added = 0
    while added < days:
        cur += timedelta(days=1)
        d = cur.date()
        if d in extra or (cur.weekday() < 5 and d not in holidays):
            added += 1
    return cur


def compute(
    created_at: str | datetime | None,
    urgency_level: str = "一般",
    closed: bool = False,
    now: datetime | None = None,
) -> dict:
    """计算办理时限：到期时刻、剩余时长、状态与依据条款。"""
    rules = _rules()
    levels = rules.get("levels", {})
    cfg = levels.get(urgency_level) or levels.get("一般") or {}
    start = _parse_dt(created_at)
    now = now or datetime.now()
    holidays, extra, holidays_configured = _holidays()

    notes: list[str] = []
    if "workdays" in cfg:
        days = int(cfg["workdays"])
        if get_settings().deadline_workdays_only:
            due = _add_workdays(start, days, holidays, extra)
            mode = "工作日"
            if not holidays_configured:
                notes.append("未配置法定节假日数据，仅按周末计算工作日（节假日顺延未计入）")
        else:
            due = start + timedelta(days=days)
            mode = "自然日"
        total_hours = (due - start).total_seconds() / 3600
    else:
        hours = int(cfg.get("hours", 24))
        due = start + timedelta(hours=hours)
        mode = cfg.get("mode", "自然日")
        total_hours = float(hours)

    if cfg.get("value_status"):
        notes.append(f"一般件时限为{cfg['value_status']}")

    remaining = (due - now).total_seconds() / 3600
    near_threshold = max(float(rules.get("near_due_min_hours", 4)), total_hours * float(rules.get("near_due_ratio", 0.2)))
    if closed:
        state = "已办结"
    elif remaining < 0:
        state = "超期"
    elif remaining <= near_threshold:
        state = "临期"
    else:
        state = "正常"

    clauses = rules.get("legal_basis", {}).get("clauses", {})
    basis_clause = clauses.get(cfg.get("clause_key", ""), "")

    result = {
        "level": urgency_level,
        "label": cfg.get("label", ""),
        "due_at": due.isoformat(timespec="minutes"),
        "mode": mode,
        "total_hours": round(total_hours, 1),
        "remaining_hours": round(remaining, 1),
        "state": state,
        "near_due_threshold_hours": round(near_threshold, 1),
        "basis": {
            "name": rules.get("legal_basis", {}).get("name", ""),
            "clause": basis_clause,
        },
        "commitment_note": rules.get("commitment_note", "") if urgency_level == "一般" else "",
        "notes": notes,
    }
    if state == "超期":
        result["supervision"] = (
            "已超期：建议按规范启动督办（群众多次反映、承办单位办理不到位的，"
            "热线可联合政府督查机构开展专项督办）。"
        )
    elif state == "临期":
        result["supervision"] = "即将到期：建议提醒承办单位按时反馈进展。"
    return result

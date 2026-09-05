"""工单质量检查（规则式，无 LLM 成本）：完整性 / 一致性 / 风险项校验。

返回结构化检查结果供前端展示；每项 passed / warn 两态，warn 不阻断流转。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.core.config import get_settings

PENDING_MARKS = ("待确认", "无", "不详", "未知", "")


def _filled(value: str | None) -> bool:
    v = (value or "").strip()
    return v not in PENDING_MARKS


def run_qc(case: Any) -> list[dict]:
    """对案件当前各节产物跑规则校验。case 需带 understanding/work_order/... 属性。"""
    checks: list[dict] = []
    u = case.understanding
    wo = case.work_order
    cls = case.classification
    rt = case.routing
    rd = case.reply_draft

    # ---- 完整性：关键要素 ----
    if u is not None:
        els = u.elements or {}
        core_keys = [k for k in els.keys() if k in ("地点", "location", "事发地点") or "地点" in k]
        location_filled = any(_filled(str(els[k])) for k in core_keys)
        checks.append({
            "item": "事发地点已明确",
            "passed": location_filled,
            "detail": "" if location_filled else "地点缺失或待确认，可能影响属地转派",
        })
        time_keys = [k for k in els.keys() if "时间" in k or k in ("time",)]
        time_filled = any(_filled(str(els[k])) for k in time_keys)
        checks.append({
            "item": "事发时间已明确",
            "passed": time_filled,
            "detail": "" if time_filled else "时间待确认，答复时限计算可能受影响",
        })

    # ---- 完整性：工单字段 ----
    if wo is not None:
        empty_fields = [
            label for label, val in [
                ("事件描述", wo.event_description), ("诉求事项", wo.handling_request), ("标题", wo.title),
            ] if not _filled(val)
        ]
        checks.append({
            "item": "工单核心字段完整",
            "passed": not empty_fields,
            "detail": "" if not empty_fields else "缺失：" + "、".join(empty_fields),
        })

    # ---- 一致性：分类 ----
    if cls is not None:
        checks.append({
            "item": "事项类别已确定",
            "passed": cls.category_code is not None,
            "detail": "" if cls.category_code else "无法归类，须人工判断后再转派",
        })
        low_conf = cls.confidence < 0.5
        checks.append({
            "item": "分类置信度达标（≥50%）",
            "passed": not low_conf,
            "detail": "" if not low_conf else f"当前置信度 {int(cls.confidence * 100)}%，建议人工复核",
        })

    # ---- 一致性：转派 ----
    if rt is not None:
        checks.append({
            "item": "已指定首要承办单位",
            "passed": bool(rt.primary),
            "detail": "" if rt.primary else "无明确 primary，须人工指定",
        })
        if rt.needs_human_judgment:
            checks.append({
                "item": "职责边界清晰",
                "passed": False,
                "detail": rt.judgment_note or "职责交叉，需人工裁断承办单位",
            })

    # ---- 风险项 ----
    if u is not None and u.urgent:
        checks.append({
            "item": "紧急件已附人工处置提示",
            "passed": bool(u.manual_action),
            "detail": "" if u.manual_action else "紧急件但无 manual_action，须补充",
        })
    if u is not None and u.needs_clarification:
        checks.append({
            "item": "待补信息已列明",
            "passed": len(u.missing_fields or []) > 0,
            "detail": "" if u.missing_fields else "标记待补充但未列出缺什么",
        })

    # ---- 合规：回复 ----
    if rd is not None:
        checks.append({
            "item": "答复含受理确认开头",
            "passed": ("收悉" in rd.reply_text) and ("您好" in rd.reply_text),
            "detail": "" if ("收悉" in rd.reply_text and "您好" in rd.reply_text) else "答复缺少规范开头",
        })
        bad_refs = _invalid_policy_refs(rd.policy_refs or [])
        checks.append({
            "item": "政策引用真实可溯",
            "passed": not bad_refs,
            "detail": "" if not bad_refs else "不在政策库中的引用：" + "；".join(bad_refs),
        })

    return checks


def _invalid_policy_refs(refs: list[str]) -> list[str]:
    """合法引用 = 精选法规 ∪ 已入库上传文档；名称匹配允许省略版本/日期括注。"""
    settings = get_settings()
    path: Path = settings.data_dir / "policies" / "policy_references.json"
    valid: set[str] = set()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for p in data.get("policies", []):
            valid.add(p["name"])
    try:
        from app.services import policy_rag

        valid.update(d["source_name"] for d in policy_rag.list_documents())
    except Exception:  # noqa: BLE001 - RAG 不可用时仅校验精选库
        pass
    if not valid:
        return refs  # 两个来源都空时任何引用都视为可疑

    def _norm(name: str) -> str:
        return re.sub(r"（[^）]*）|\([^)]*\)", "", name).strip("《》 ").strip()

    short_names = {_norm(v) for v in valid}
    invalid = []
    for r in refs:
        if r in valid or _norm(r) in short_names:
            continue
        invalid.append(r)
    return invalid

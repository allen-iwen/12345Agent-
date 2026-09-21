# -*- coding: utf-8 -*-
"""答复合规审查（支柱四 · 答复把关）。

设计要点：
1. 规则为**确定性主判**（词表 + 正则 + 结构检查），命中位置可定位到原文片段，可解释、可审计；
2. LLM 复核仅在 `llm_review_enabled` 时补充**语义级**发现（语气失当、责任规避、未正面回应），
   且不得增删规则命中——避免模型自由发挥改变合规判定；
3. 依据《安徽省12345热线诉求闭环办理工作规范》答复环节要求（必须正面回应诉求、列明政策依据，
   经热线审核不规范的将退回重办），输出「退回重办风险等级」与修改建议；
4. 政策引用真实性复用 `qc._invalid_policy_refs`，不重复实现。
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.services import llm

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}
_RISK_BY_RANK = {3: "高", 2: "中", 1: "低", 0: "无"}


@lru_cache
def _rules() -> dict:
    path = get_settings().data_dir / "compliance" / "reply_rules.json"
    if not path.exists():
        logger.warning("reply_rules.json 缺失，合规审查降级为无规则")
        return {"rules": [], "risk_levels": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def available() -> bool:
    return bool(_rules().get("rules"))


def _find_keyword_hits(text: str, keywords: list[str]) -> list[tuple[str, int]]:
    hits: list[tuple[str, int]] = []
    for kw in keywords or []:
        start = text.find(kw)
        if start >= 0:
            hits.append((kw, start))
    return hits


def _find_pattern_hits(text: str, patterns: list[str]) -> list[tuple[str, int]]:
    hits: list[tuple[str, int]] = []
    for p in patterns or []:
        for m in re.finditer(p, text):
            hits.append((m.group(0), m.start()))
    return hits


def _bigrams(text: str) -> set[str]:
    """中文二元组（去标点），用于判断答复是否回应了诉求主题。"""
    clean = re.sub(r"[^\u4e00-\u9fa5]", "", text or "")
    return {clean[i : i + 2] for i in range(len(clean) - 1)}


_STOP_BIGRAM_CHARS = set("的了是在和与及或有个我你他她它们这那为对于关于请您好谢谢市民群众反映投诉问题已收悉")


def _distinctive_terms(text: str) -> set[str]:
    return {b for b in _bigrams(text) if not (set(b) & _STOP_BIGRAM_CHARS)}


def _addresses_request(reply_text: str, request_text: str) -> bool:
    """答复是否正面回应诉求：与诉求原文有 ≥3 个特征二元组重叠。"""
    if len(reply_text or "") < 40:
        return False
    overlap = _distinctive_terms(reply_text) & _distinctive_terms(request_text)
    return len(overlap) >= 3


def _safety_needed(context: dict) -> bool:
    urgency = (context or {}).get("urgency") or {}
    if urgency.get("level") in ("特急", "紧急"):
        return True
    return bool((context or {}).get("manual_action"))


def _llm_semantic_review(reply_text: str, request_text: str) -> list[dict]:
    """可选 LLM 语义复核：只补充发现，不改变规则命中。"""
    if not get_settings().llm_review_enabled:
        return []
    system = (
        "你是12345热线答复的合规复核员。请只指出以下三类**语义级**问题，不重复列举用词问题：\n"
        "1) 语气失当（生硬、推责、情绪化）；2) 责任规避（回避本部门应尽职责）；"
        "3) 未正面回应诉求（答非所问、只讲流程不回应当事诉求）。\n"
        "输出 JSON：{\"findings\": [{\"kind\": \"语气失当|责任规避|未正面回应\", \"quote\": \"原文片段\", \"suggestion\": \"修改建议\"}]}\n"
        "若无问题输出 {\"findings\": []}。"
    )
    user = f"群众诉求：\n{request_text[:800]}\n\n草拟答复：\n{reply_text[:1200]}\n\n请复核。"
    try:
        data = llm.chat_json(system, user, temperature=0.0, max_tokens=1500)
    except Exception as exc:  # noqa: BLE001 - 复核失败不影响规则结论
        logger.warning("答复合规 LLM 复核失败：%s", exc)
        return []
    out = []
    for f in data.get("findings", []) or []:
        quote = str(f.get("quote", "")).strip()
        out.append({
            "type": "llm_semantic",
            "label": str(f.get("kind", "语义问题")).strip() or "语义问题",
            "severity": "medium",
            "quote": quote[:60],
            "index": reply_text.find(quote[:20]) if quote else -1,
            "suggestion": str(f.get("suggestion", "")).strip(),
            "source": "LLM 复核",
        })
    return out


def audit(
    reply_text: str,
    policy_refs: list[str] | None = None,
    context: dict | None = None,
    decision_signals: dict | None = None,
) -> dict:
    """对草拟答复做合规审查，返回风险等级、问题清单与修改建议。

    context 可含：raw_text / event_description / urgency / manual_action。
    decision_signals：System One 决策模型对答复三维（过度承诺/未正面回应/隐私）的判断（可选）。
    """
    rules = _rules()
    text = reply_text or ""
    ctx = context or {}
    request_text = f"{ctx.get('raw_text', '')} {ctx.get('event_description', '')}"
    findings: list[dict] = []

    for rule in rules.get("rules", []):
        rtype = rule.get("type", "")
        label = rule.get("label", rtype)
        severity = rule.get("severity", "low")
        suggestion = rule.get("suggestion", "")

        hits: list[tuple[str, int]] = []
        hits += _find_keyword_hits(text, rule.get("keywords") or [])
        hits += _find_pattern_hits(text, rule.get("patterns") or [])

        check = rule.get("check")
        if check == "addresses_request" and not _addresses_request(text, request_text):
            hits.append(("未回应诉求主题", -1))
        elif check == "safety_tip_required" and _safety_needed(ctx):
            if not any(k in text for k in rules.get("safety_keywords", [])):
                hits.append(("缺少安全提示", -1))
        elif check == "required_elements":
            # 开头要素为必须同时具备；结尾致谢为「任一即可」
            missing = [k for k in rules.get("required_open_keywords", []) if k not in text]
            close_kws = rules.get("required_close_keywords", [])
            if close_kws and not any(k in text for k in close_kws):
                missing.append("结尾致谢（" + "/".join(close_kws) + "）")
            if missing:
                hits.append(("缺少：" + "、".join(missing), -1))
        elif check == "policy_refs" and policy_refs:
            try:
                from app.services import qc

                bad = qc._invalid_policy_refs(policy_refs)  # noqa: SLF001 - 复用既有校验
            except Exception:  # noqa: BLE001
                bad = []
            hits += [(b, text.find(b)) for b in bad]

        seen: set[str] = set()
        for quote, idx in hits:
            if rtype in seen:  # 同类问题只保留首个命中，避免同一规则重复罗列
                break
            seen.add(rtype)
            findings.append({
                "type": rtype,
                "label": label,
                "severity": severity,
                "quote": quote,
                "index": idx,
                "suggestion": suggestion,
                "source": "规则",
            })

    findings += _llm_semantic_review(text, request_text)

    # System One 决策模型的三维判断（可选）：只补充发现，不改变规则命中
    model = (decision_signals or {}).get("conclusions") or {}
    if (decision_signals or {}).get("available") and model:
        if (model.get("reply_overpromise_score") or 0) >= 1.5:
            findings.append({
                "type": "overpromise", "label": "过度承诺（模型判定）", "severity": "high",
                "quote": f"承诺程度分 {model.get('reply_overpromise_score')}", "index": -1,
                "suggestion": "改为按程序表述，如「将依法依规核实处理」，不承诺具体结果",
                "source": "决策模型",
            })
        if model.get("reply_addresses_request") is False:
            findings.append({
                "type": "no_direct_response", "label": "未正面回应诉求（模型判定）", "severity": "medium",
                "quote": "未回应诉求主题", "index": -1,
                "suggestion": "答复须正面回应群众诉求：核查情况、办理方向、依据或措施、后续安排",
                "source": "决策模型",
            })
        if model.get("reply_privacy") is True:
            findings.append({
                "type": "privacy_leak", "label": "隐私信息泄露风险（模型判定）", "severity": "high",
                "quote": "疑似含个人敏感信息", "index": -1,
                "suggestion": "删除手机号、身份证号、精确门牌；统一用「您」指代",
                "source": "决策模型",
            })

    top = max((_SEVERITY_RANK.get(f["severity"], 1) for f in findings), default=0)
    risk = _RISK_BY_RANK.get(top, "无")
    hints: list[str] = []
    for f in findings:
        if f["suggestion"] and f["suggestion"] not in hints:
            hints.append(f["suggestion"])

    legal = rules.get("legal_basis", {})
    return {
        "risk_level": risk,
        "risk_note": (rules.get("risk_levels", {}) or {}).get(risk, ""),
        "findings": findings,
        "rewrite_hint": hints,
        "checked_rules": len(rules.get("rules", [])),
        "llm_reviewed": any(f.get("source") == "LLM 复核" for f in findings) or bool(
            get_settings().llm_review_enabled
        ),
        "basis": {
            "name": legal.get("name", ""),
            "clause": (legal.get("clauses") or [""])[0],
        },
    }

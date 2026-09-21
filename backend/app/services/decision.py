# -*- coding: utf-8 -*-
"""System One 决策原语适配层（Jev / TypeSafe）。

与 LLM 的分工：**判断交给决策模型，写作交给生成模型**。
- 决策模型（Jev）只回答带类型的问题并给出**校准概率**，不生成文字；
- 一次请求可并行问多个独立问题（speculative fan-out），长 state 只发送一次，成本与延迟极低；
- 概率与置信度直接支撑「高→自动采用 / 中→人工确认 / 低→转人工」的**置信度门控**，
  这正好为「职责交叉、拿不准就交人工」提供有依据的阈值，而不是拍脑袋。

契约（来自 https://api.typesafe.ai/openapi.json）：
  POST {base}/v1/systemone
  body: {state, model, questions}
  resp: {model, answers: {id: {type, noul|choice|score, probabilities?, confidence?}}, usage}
  GET  {base}/v1/models

三类问题原语：
- noul  是/否 → 返回 noul（为「是」的概率）
- choice 从选项中选一 → choice + probabilities + confidence
- score  在刻度上的位置 → score + legend + probabilities + confidence

设计约束（与图片证据服务一致）：
1. 未配置或用尽重试后仍失败 → 返回 available=False，调用方回退到既有规则/LLM 路径，零回归；
2. 响应中的**实际模型版本号必须记录**（别名会漂移，阈值需与版本绑定）；
3. 只把问题真正需要的文本放进 state（官方明确：state 臃肿会降低准确率）。
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _cfg() -> dict:
    s = get_settings()
    if s.decision_provider == "laya":
        # 本地开源 System One 决策模型（Apache 2.0）：非自回归、单次前向、CPU 可跑
        return {"provider": "laya", "model": s.decision_model_path or "convaiinnovations/laya",
                "subfolder": s.decision_laya_subfolder, "device": s.decision_laya_device}
    if s.decision_provider == "vercel":
        # Vercel AI Gateway：模型 id 形如 typesafe-ai/jev（网关按模型路由到 TypeSafe）
        return {"provider": "vercel", "base_url": "https://ai-gateway.vercel.sh",
                "api_key": s.decision_api_key, "model": s.decision_model or "typesafe-ai/jev"}
    if s.decision_provider == "typesafe":
        return {"provider": "typesafe", "base_url": s.decision_base_url.rstrip("/"),
                "api_key": s.decision_api_key, "model": s.decision_model or "jev-latest"}
    return {}


def available() -> bool:
    cfg = _cfg()
    if cfg.get("provider") == "laya":
        try:
            import laya  # noqa: F401

            return True
        except ImportError:
            return False
    return bool(cfg.get("api_key") and cfg.get("base_url"))


def enabled() -> bool:
    return get_settings().decision_enabled and available()


def status() -> dict:
    cfg = _cfg()
    s = get_settings()
    return {
        "available": available(),
        "enabled": s.decision_enabled,
        "provider": cfg.get("provider") or "none",
        "model": cfg.get("model", ""),
        "thresholds": {"high": s.decision_high_conf, "low": s.decision_low_conf},
    }


def noul(instructions: str, criteria: dict | None = None) -> dict:
    q: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if criteria:
        q["criteria"] = criteria
    return q


def choice(instructions: str, criteria: dict[str, str | None]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions: str, criteria: list[str]) -> dict:
    return {"type": "score", "instructions": instructions, "criteria": criteria}


def gate(confidence: float | None) -> str:
    """置信度门控：high→auto（可自动采用）/ medium→confirm（人工确认）/ low→human（转人工）。"""
    s = get_settings()
    if confidence is None:
        return "confirm"
    if confidence >= s.decision_high_conf:
        return "auto"
    if confidence < s.decision_low_conf:
        return "human"
    return "confirm"


# ---------------- 本地开源决策模型 laya（Apache 2.0）----------------
# 与 Jev 同类：非自回归 System 1，单次前向返回带类型的校准概率；权重开源、可离线、$0 成本。
# 中文场景必须用 multilingual 检查点（根检查点仅英文，非拉丁文字会崩）。

_laya_agent = None
_laya_error = ""
_laya_lock = __import__("threading").Lock()


def _get_laya(cfg: dict):
    global _laya_agent, _laya_error
    if _laya_agent is not None or _laya_error:
        return _laya_agent
    with _laya_lock:
        if _laya_agent is not None or _laya_error:
            return _laya_agent
        try:
            import laya

            t0 = __import__("time").monotonic()
            path = cfg.get("model") or "convaiinnovations/laya"
            sub = cfg.get("subfolder") or "multilingual"
            try:
                _laya_agent = laya.load(path)  # 本地目录
            except Exception:  # noqa: BLE001 - 非本地路径则按仓库 + 子目录加载
                _laya_agent = laya.load(path, subfolder=sub)
            # 官方「Honest Limits」：高基数 Choice 需提高每选项 token 预算，否则选项文本互相不可分
            s = get_settings()
            try:
                if s.decision_laya_head_max_len:
                    _laya_agent.cfg["head_max_len"] = s.decision_laya_head_max_len
                if s.decision_laya_max_len:
                    _laya_agent.cfg["max_len"] = s.decision_laya_max_len
            except Exception:  # noqa: BLE001 - 配置字段不可写则忽略
                pass
            logger.info("laya 决策模型已加载（%s/%s，%.0fs，head_max_len=%s）",
                        path, sub, __import__("time").monotonic() - t0,
                        getattr(_laya_agent, "cfg", {}).get("head_max_len"))
        except Exception as exc:  # noqa: BLE001
            _laya_error = str(exc)
            logger.warning("laya 加载失败：%s", exc)
    return _laya_agent


def warm() -> None:
    """后台线程预热本地决策模型（首次加载约 30–40s，避免首个请求卡顿）。"""
    import threading

    cfg = _cfg()
    if cfg.get("provider") == "laya":
        threading.Thread(target=_get_laya, args=(cfg,), daemon=True, name="laya-warmup").start()


def _ask_laya(state: str | dict | list, questions: dict[str, dict], cfg: dict) -> dict:
    if not questions:
        return {"available": False, "note": "questions 为空"}
    agent = _get_laya(cfg)
    if agent is None:
        return {"available": False, "note": f"laya 模型不可用：{_laya_error}"}
    try:
        raw = agent.predict(state, questions)
    except Exception as exc:  # noqa: BLE001 - 调用失败回退
        logger.warning("laya 推理失败：%s", exc)
        return {"available": False, "note": f"laya 推理失败：{exc}"}

    norm: dict[str, dict] = {}
    for qid, a in (raw.get("answers") or {}).items():
        if not isinstance(a, dict):
            continue
        qtype = a.get("type")
        if qtype == "noul":
            norm[qid] = {"type": "noul", "value": a.get("noul"), "confidence": a.get("confidence"),
                         "gate": gate(None)}  # noul 无独立 confidence，由调用方按概率设阈
        elif qtype == "choice":
            norm[qid] = {"type": "choice", "value": a.get("choice"),
                         "probabilities": a.get("probabilities") or {},
                         "confidence": a.get("confidence"), "gate": gate(a.get("confidence"))}
        elif qtype == "score":
            norm[qid] = {"type": "score", "value": a.get("score"), "legend": a.get("legend") or {},
                         "probabilities": a.get("probabilities") or {},
                         "confidence": a.get("confidence"), "gate": gate(a.get("confidence"))}
    return {
        "available": True,
        "provider": "laya",
        "model": f"laya-{cfg.get('subfolder') or 'multilingual'}",
        "requested_model": cfg.get("model"),
        "answers": norm,
        "usage": {},
        "cost_usd": 0.0,  # 自托管开源模型：调用成本为 0
        "routing": raw.get("routing"),
    }


def ask(state: str | dict | list, questions: dict[str, dict], model: str | None = None) -> dict:
    """发起一次 System One 评估；失败或未配置时返回 available=False（调用方回退）。"""
    cfg = _cfg()
    if cfg.get("provider") == "laya":
        return _ask_laya(state, questions, cfg)
    if not (cfg.get("api_key") and cfg.get("base_url")):
        return {"available": False, "note": "未配置决策模型（DECISION_PROVIDER / DECISION_API_KEY）"}
    if not questions:
        return {"available": False, "note": "questions 为空"}

    s = get_settings()
    url = cfg["base_url"] + "/v1/systemone"
    body = {"model": model or cfg["model"], "state": state, "questions": questions}
    try:
        resp = requests.post(
            url,
            headers={"Authorization": "Bearer " + cfg["api_key"], "Content-Type": "application/json"},
            json=body,
            timeout=s.decision_timeout_s,
        )
    except Exception as exc:  # noqa: BLE001 - 网络异常回退
        logger.warning("决策模型调用失败：%s", exc)
        return {"available": False, "note": f"决策模型调用失败：{exc}"}

    if resp.status_code != 200:
        note = f"{cfg['provider']} HTTP {resp.status_code}: {resp.text[:160]}"
        if resp.status_code in (429, 529):
            note += "（限流/过载，建议指数退避重试）"
        logger.warning("决策模型返回错误：%s", note)
        return {"available": False, "note": note}

    payload = resp.json()
    answers = payload.get("answers") or {}
    norm: dict[str, dict] = {}
    for qid, a in answers.items():
        if not isinstance(a, dict):
            continue
        item = {"type": a.get("type")}
        if a.get("type") == "noul":
            item["value"] = a.get("noul")
            item["gate"] = gate(None)  # Noul 无 confidence，调用方按概率自行设阈值
        elif a.get("type") == "choice":
            item["value"] = a.get("choice")
            item["probabilities"] = a.get("probabilities") or {}
            item["confidence"] = a.get("confidence")
            item["gate"] = gate(a.get("confidence"))
        elif a.get("type") == "score":
            item["value"] = a.get("score")
            item["legend"] = a.get("legend") or {}
            item["probabilities"] = a.get("probabilities") or {}
            item["confidence"] = a.get("confidence")
            item["gate"] = gate(a.get("confidence"))
        norm[qid] = item

    usage = payload.get("usage") or {}
    model_version = payload.get("model") or body["model"]
    logger.info("决策模型应答 model=%s questions=%d input_tokens=%s",
                model_version, len(norm), usage.get("input_tokens"))
    return {
        "available": True,
        "provider": cfg["provider"],
        "model": model_version,
        "requested_model": body["model"],
        "answers": norm,
        "usage": usage,
        # 成本参考：输入 $0.042/百万 token，输出免费（用于赛事材料的成本对比）
        "cost_usd": round(float(usage.get("input_tokens") or 0) * 0.042 / 1_000_000, 8),
    }

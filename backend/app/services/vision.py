# -*- coding: utf-8 -*-
"""多模态图片证据分析（受理把关）。

用途：市民/坐席上传现场照片（井盖缺失、道路破损、垃圾堆积、违章建筑、消防通道堵塞等），
由视觉模型抽取「隐患类型 / 严重程度 / 可见要素」，作为依据链的一部分影响事项分类与急件分级。

设计要点：
1. provider 可插拔（minimax / qianfan，均为 OpenAI 兼容 chat/completions 的 image_url 形态），
   主 provider 失败时自动降级备用 provider；
2. 严格约束：只描述图片可见事实、不推测身份、不输出人脸/车牌/门牌等个人信息（合规要求）；
3. 不可用时返回 available=False（链路行为与无图片时完全一致，零回归），前端提示人工判读；
4. 图片 ≤10MB（服务端上限），以 data URL 形式内联，避免外链与额外上传。
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from pathlib import Path

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024

SYSTEM = """你是芜湖市12345热线的「图片证据分析员」。市民上传的现场照片用于辅助判断事项类别与紧急程度。
只依据图片中**可见的事实**输出 JSON：
{"hazard": true/false, "hazard_type": "井盖缺失|道路破损|垃圾堆积|违章建筑|占道经营|消防通道堵塞|电线坠落|积水内涝|绿化损坏|其他|无隐患",
 "severity": "特急|紧急|一般", "summary": "一句话客观描述", 
 "elements": {"可见对象": "", "地点线索": "", "规模范围": ""}, "confidence": 0.0}

约束（必须遵守）：
1. 只描述图片中确实可见的内容，不推测拍摄者身份、不判断地点真伪、不脑补画面外信息；
2. 严禁输出人脸特征、车牌号、门牌号、姓名、手机号等任何个人信息；
3. severity 仅在存在人身安全隐患时给「特急」（如井盖缺失、电线坠落、燃气泄漏迹象、消防通道堵塞、危房），
   影响面较大但无即时人身危险给「紧急」，其余给「一般」；
4. 图片与诉求无关、或未发现隐患时：hazard=false, hazard_type="无隐患", severity="一般"；
5. confidence 表示你对判断的把握（0~1）。"""


def _provider_cfg(name: str) -> dict:
    """按 provider 名取配置；空名返回空配置。"""
    s = get_settings()
    if name == "minimax" or (name == "" and s.vision_provider == "minimax"):
        return {"provider": "minimax", "base_url": s.vision_base_url, "api_key": s.vision_api_key, "model": s.vision_model}
    if name == "qianfan":
        return {
            "provider": "qianfan",
            "base_url": s.vision_fallback_base_url or "https://qianfan.baidubce.com/v2",
            "api_key": s.vision_fallback_api_key,
            "model": s.vision_fallback_model,
        }
    return {}


def _active_providers() -> list[dict]:
    s = get_settings()
    out: list[dict] = []
    primary = _provider_cfg(s.vision_provider)
    if primary.get("api_key") and primary.get("base_url"):
        out.append(primary)
    fb = _provider_cfg(s.vision_fallback_provider) if s.vision_fallback_provider else {}
    if fb.get("api_key") and fb.get("base_url"):
        out.append(fb)
    return out


def available() -> bool:
    return bool(_active_providers())


def _data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def _parse_json(content: str) -> dict:
    """宽松解析：优先复用 llm 的解析器，失败则取首个 JSON 对象。"""
    try:
        from app.services import llm

        return llm._extract_json(content)  # noqa: SLF001 - 复用既有宽松解析
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", content, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise ValueError(f"视觉模型输出无法解析为 JSON：{content[:200]}")


def _call(cfg: dict, data_url: str, context_text: str) -> dict:
    s = get_settings()
    user_content = [
        {"type": "text", "text": f"诉求上下文（供参考，不得据此脑补画面外信息）：\n{context_text or '（无）'}\n\n请分析图片并输出 JSON。"},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    body = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_content},
        ],
        "max_completion_tokens": 1200,
        "temperature": 0.1,
        "thinking": {"type": "disabled"},  # MiniMax-M3 关闭思考链；不支持该参数的服务会忽略
    }
    resp = requests.post(
        cfg["base_url"].rstrip("/") + "/chat/completions",
        headers={"Authorization": "Bearer " + cfg["api_key"], "Content-Type": "application/json"},
        json=body,
        timeout=s.vision_timeout_s,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"{cfg['provider']} HTTP {resp.status_code}: {resp.text[:160]}")
    payload = resp.json()
    content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not content.strip():
        raise RuntimeError(f"{cfg['provider']} 返回空内容")
    data = _parse_json(content)
    elements = data.get("elements") or {}
    if not isinstance(elements, dict):
        elements = {"可见对象": str(elements)}
    return {
        "available": True,
        "provider": cfg["provider"],
        "model": cfg["model"],
        "hazard": bool(data.get("hazard", False)),
        "hazard_type": str(data.get("hazard_type", "")).strip() or "其他",
        "severity": str(data.get("severity", "一般")).strip() or "一般",
        "summary": str(data.get("summary", "")).strip(),
        "elements": {str(k): str(v) for k, v in elements.items() if str(v).strip()},
        "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.0) or 0.0))),
    }


def analyze(image_path: str | Path, context_text: str = "") -> dict:
    """分析图片证据；provider 不可用或全部失败时返回 available=False（不阻断链路）。"""
    path = Path(image_path)
    providers = _active_providers()
    if not providers:
        return {"available": False, "note": "未配置视觉模型（VISION_PROVIDER），请人工判读图片"}
    if not path.exists():
        return {"available": False, "note": f"图片不存在：{path}"}
    if path.stat().st_size > MAX_IMAGE_BYTES:
        return {"available": False, "note": "图片超过 10MB 上限，建议压缩后重传"}

    try:
        data_url = _data_url(path)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "note": f"图片编码失败：{exc}"}

    errors: list[str] = []
    for cfg in providers:
        try:
            out = _call(cfg, data_url, context_text)
            if errors:
                out["fallback_note"] = "；".join(errors)
            return out
        except Exception as exc:  # noqa: BLE001 - 逐个 provider 降级
            errors.append(f"{cfg['provider']}：{exc}")
            logger.warning("视觉分析失败（%s）：%s", cfg["provider"], exc)
    return {"available": False, "note": "视觉模型调用失败：" + "；".join(errors)}

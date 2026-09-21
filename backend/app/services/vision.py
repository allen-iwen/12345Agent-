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

【隐患类型判定优先级】多种隐患并存时，按人身安全优先：
消防通道堵塞 ＞ 电线坠落 ＞ 井盖缺失 ＞ 违章建筑/危房 ＞ 道路破损/积水 ＞ 垃圾堆积 ＞ 占道经营 ＞ 绿化损坏。
例：楼道/出入口被成堆垃圾完全堵死 → 判「消防通道堵塞」（而非垃圾堆积）。

【严重程度判据】（按情境对号入座，不要凭感觉给中间值）
- 特急：存在人身伤亡风险或需立即处置。情境示例：
  井盖缺失致行人坠落、电线坠落或线缆低垂可触及、消防/疏散通道被完全堵塞、
  燃气泄漏迹象、危房或结构随时可能坍塌。
- 紧急：无即时人身危险，但影响公共秩序、环境卫生或多人正常生活。情境示例：
  成片/大量垃圾堆积或垃圾外溢、占道经营阻碍人行通行、私搭乱建存在结构或消防间距隐患、
  道路大面积破损或塌陷影响车辆通行、路面积水没及行人。
- 一般：局部、轻微，不影响安全与通行。情境示例：
  小面积路面破损、零星少量垃圾、单一绿化损坏、仅询问或反映但画面无明显问题。

约束（必须遵守）：
1. 只描述图片中确实可见的内容，不推测拍摄者身份、不判断地点真伪、不脑补画面外信息；
2. 严禁输出人脸特征、车牌号、门牌号、姓名、手机号等任何个人信息；
3. 隐患细节较小但确实存在时（如低垂线缆、被堵的疏散门），应判为隐患而不是"未见隐患"，
   并在 summary 中指出可见依据；确实没有可见依据时才判 hazard=false；
4. 图片与诉求无关、或未发现隐患时：hazard=false, hazard_type="无隐患", severity="一般"；
5. confidence 表示你对判断的把握（0~1）；
6. **输出必须是可解析的 JSON：字符串内部禁止出现英文双引号，需要引用招牌、店名等文字时一律用「」包裹。**"""


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
    """宽松解析：优先复用 llm 的解析器，失败则取首个 JSON 对象，再失败则修复串内引号。"""
    try:
        from app.services import llm

        return llm._extract_json(content)  # noqa: SLF001 - 复用既有宽松解析
    except Exception:  # noqa: BLE001
        pass
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise ValueError(f"视觉模型输出无法解析为 JSON：{content[:200]}")
    raw = m.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 修复常见问题：字符串值内部出现未转义的英文双引号（模型引用店名/招牌时高发）
    # 策略：把出现在中文或字母之间、且两侧无 JSON 语法意义的引号替换为「」
    repaired = re.sub(r'(?<=[\u4e00-\u9fa5A-Za-z0-9])"(?=[\u4e00-\u9fa5A-Za-z0-9])', "」", raw)
    repaired = re.sub(r'(?<=[\u4e00-\u9fa5])」(?=[^,}\]])', "」", repaired)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as exc:
        raise ValueError(f"视觉模型输出无法解析为 JSON（已尝试修复）：{exc}；原文：{content[:200]}") from exc


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

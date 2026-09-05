"""转写文本降噪整理：把语音听写原文整理为可读通话记录。

真实来电转写里的典型噪声（来自实测语料）：
1. 彩铃/提示音被误识别成无意义串（"噢b二三四五""c噢b"）；
2. 口语填充词与语气词（嗯、唉、啊、就是、那个）；
3. 口吃重复（"前两嗯前前一段时间"）；
4. 坐席与市民对话混杂、无分段。

处理原则（可审计，防幻觉）：
- 只做"删噪声、并重复、分段落"，**事实信息（时间/地点/人名/数字/诉求）逐字保留**；
- 整理稿字数不得低于原文的 45%，低于则视为模型过度删改，弃用整理稿回退原文；
- 原文永远保留并随响应返回（前端可切换），不覆盖证据。
"""
from __future__ import annotations

import logging

from app.services.llm import chat_json

logger = logging.getLogger(__name__)

MIN_KEEP_RATIO = 0.45  # 整理稿最短保留比例（低于判定为过度删改）
MIN_CHARS = 120  # 原文低于该长度不值得整理

_SYSTEM = """你是12345政务热线的通话记录整理员。输入是一段热线录音的语音听写原文（可能来自云端或本地引擎），其中混杂：
- 彩铃/提示音被误识别的无意义串（如"噢b二三四五"）；
- 口语填充词（嗯、唉、啊、就是、那个、对吧）；
- 口吃与重复（"前两嗯前前一段时间"）；
- 坐席与市民的对话交织、缺少分段。

请整理为规范的通话记录，规则：
1. 只删除与诉求完全无关的提示音误识别串与纯填充词（嗯、唉、啊这类语气衬字）；
2. 合并口吃重复为一次完整表达；
3. 事实信息（时间、地点、人名、单位、数字、诉求内容）必须逐字保留，禁止改写、概括、新增或脑补；
4. 禁止概括、禁止省略任何对话轮次——坐席的问候、回读确认（如复述姓名电话地址）、进度说明都是记录的一部分，必须保留；
5. 若能辨识对话轮次（坐席问候/回读确认 vs 市民陈述），用「坐席：」「市民：」分段；辨识不了就按语义分段；
6. 保留原有标点习惯，必要时按语义补足标点；
7. 整理稿长度通常应为原文的 60%～90%（只删噪声，不做摘要压缩）。

输出 JSON：
{"clean": "整理后的通话记录", "changes": ["删除开头彩铃误识别串", "合并口吃重复", ...], "speaker_labeled": true/false}
changes 用不超过5条短句说明做了哪类整理。"""

_USER = """通话时长约 {dur:.0f} 秒。听写原文如下：

{text}"""


def clean_transcript(text: str, duration_s: float = 0.0) -> dict:
    """整理转写原文；失败或过度删改时回退原文并说明原因。"""
    text = (text or "").strip()
    if len(text) < MIN_CHARS:
        return {"clean": text, "changes": [], "speaker_labeled": False, "applied": False, "note": "原文较短，未整理"}
    try:
        data = chat_json(_SYSTEM, _USER.format(dur=duration_s or 0, text=text), temperature=0.1)
    except Exception as exc:  # noqa: BLE001 - 整理失败不影响转写结果
        logger.warning("transcript clean failed: %s", exc)
        return {"clean": text, "changes": [], "speaker_labeled": False, "applied": False, "note": f"整理失败：{exc}"}

    clean = str(data.get("clean") or "").strip()
    if not clean or len(clean) < len(text) * MIN_KEEP_RATIO:
        return {
            "clean": text,
            "changes": [],
            "speaker_labeled": False,
            "applied": False,
            "note": f"整理稿保留率 {len(clean)}/{len(text)} 低于 {MIN_KEEP_RATIO:.0%}，已回退原文（防过度删改）",
        }
    return {
        "clean": clean,
        "changes": [str(c) for c in (data.get("changes") or [])][:5],
        "speaker_labeled": bool(data.get("speaker_labeled")),
        "applied": True,
        "note": f"已整理：{len(text)} 字 → {len(clean)} 字（去噪 {(1 - len(clean) / len(text)) * 100:.0f}%）",
    }

"""大模型调用服务：OpenAI 兼容接口（DeepSeek），强制 JSON 输出 + 重试。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    return _client


def _repair_json_literals(content: str) -> str:
    """宽松修复：把 JSON 字符串值内的裸换行/制表符转义（模型常犯，多行长文本尤甚）。"""
    out: list[str] = []
    in_str = False
    esc = False
    for ch in content:
        if in_str:
            if esc:
                esc = False
                out.append(ch)
            elif ch == "\\":
                esc = True
                out.append(ch)
            elif ch == '"':
                in_str = False
                out.append(ch)
            elif ch == "\n":
                out.append("\\n")
            elif ch == "\t":
                out.append("\\t")
            elif ch == "\r":
                pass
            else:
                out.append(ch)
        else:
            if ch == '"':
                in_str = True
            out.append(ch)
    return "".join(out)


def _extract_json(content: str) -> Any:
    """从模型输出中稳健地提取 JSON 对象。"""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

    def _try(s: str) -> Any | None:
        for cand in (s, _repair_json_literals(s)):
            try:
                return json.loads(cand)
            except json.JSONDecodeError:
                continue
        return None

    data = _try(content)
    if data is not None:
        return data
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        data = _try(match.group(0))
        if data is not None:
            return data
    raise ValueError(f"模型输出无法解析为 JSON：{content[:300]}")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def chat_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 16384,
) -> dict:
    """调用大模型并解析 JSON 对象返回。

    注意：推理型模型的 reasoning tokens 计入 max_tokens（此前 2048 会被推理
    链耗尽导致可见内容为空），预算须显著大于"可见输出+推理"之和，默认 16384。
    不要在调用点随手压小该值。
    """
    settings = get_settings()
    client = get_client()
    kwargs: dict[str, Any] = {}
    if settings.llm_json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if settings.llm_disable_thinking:
        # vLLM 部署的 Qwen 系模型：关闭内置思考链（避免思考 token 占用与格式漂移）
        kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    response = client.chat.completions.create(
        model=model or settings.llm_model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        **kwargs,
    )
    content = response.choices[0].message.content or ""
    if not content.strip():
        # 推理预算耗尽等情形会得到空内容——抛错交给 tenacity 重试，而不是静默返回空对象
        raise ValueError(
            f"模型返回空内容（finish_reason={response.choices[0].finish_reason}，"
            f"max_tokens 可能被 reasoning tokens 耗尽）"
        )
    data = _extract_json(content)
    if not isinstance(data, dict):
        raise ValueError(f"模型输出不是 JSON 对象：{content[:300]}")
    logger.info(
        "llm call ok model=%s prompt_chars=%d completion_tokens=%s",
        model or settings.llm_model,
        len(user),
        getattr(response.usage, "completion_tokens", "?"),
    )
    return data

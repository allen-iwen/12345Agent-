"""LangGraph 状态机：诉求理解 → 工单生成 → 事项分类 → 承办单位推荐 → 回复建议 → 人工审核。

人工审核作为图的中断点：review_gate 节点内 interrupt 挂起，
工作人员通过 API 确认后 resume 进入 finalize。
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from app.agents import classify, reply, route, understand, work_order
from app.core.config import get_settings
from app.services import tracing

logger = logging.getLogger(__name__)


NODE_PROMPT_KIND = {
    "understand": "诉求理解（要素/紧急/重复/缺失字段）",
    "work_order": "标准化工单生成",
    "classify": "事项分类（12 大类 + RAG）",
    "route": "承办单位推荐（职责 + 历史工单）",
    "reply": "回复建议（官方风格）",
}


def _trace(case_id: str | None, node: str, input_payload: dict):
    """返回 (record_start_fn, record_end_fn) 上下文管理器。"""
    if not case_id:
        return _noop_trace()
    return _tracing_cm(case_id, node, input_payload)


class _tracing_cm:
    def __init__(self, case_id: str, node: str, input_payload: dict) -> None:
        self.case_id = case_id
        self.node = node
        self.input_payload = input_payload
        self.run_id: int | None = None
        self.t0: float | None = None

    def __enter__(self):
        import time

        self.t0 = time.monotonic()
        self.run_id = tracing.record_start(self.case_id, self.node, NODE_PROMPT_KIND[self.node], self.input_payload)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.run_id is None or self.t0 is None:
            return
        if exc_type:
            import time

            tracing.record_end(
                self.run_id, None, error=str(exc),
                duration_ms=int((time.monotonic() - self.t0) * 1000),
            )
        # 成功时由节点自行 record_end(output)；这里只处理异常路径

    def done(self, output: dict) -> None:
        if self.run_id is not None and self.t0 is not None:
            import time

            tracing.record_end(
                self.run_id, output,
                duration_ms=int((time.monotonic() - self.t0) * 1000),
            )


class _noop_trace:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def done(self, output): pass


class CaseState(TypedDict, total=False):
    case_id: str
    raw_text: str
    source_channel: str
    clarification_context: list[str]
    vision_signals: list[dict] | None
    understanding: dict | None
    work_order: dict | None
    classification: dict | None
    routing: dict | None
    urgency: dict | None
    reply_draft: dict | None
    status: str
    review_note: str
    error: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------- 节点 ----------------


def node_understand(state: CaseState) -> dict:
    from app.schemas.models import Understanding

    with _trace(state.get("case_id"), "understand", {
        "raw_text": state.get("raw_text", ""),
        "clarification_context": state.get("clarification_context") or [],
    }) as t:
        understanding = understand.run(state["raw_text"], state.get("clarification_context") or [])
        out = understanding.model_dump()
        t.done(out)
    return {"understanding": out}


def node_work_order(state: CaseState) -> dict:
    from app.schemas.models import Understanding, WorkOrder

    with _trace(state.get("case_id"), "work_order", {
        "raw_text": state.get("raw_text", ""),
        "understanding": state.get("understanding"),
    }) as t:
        wo = work_order.run(state["raw_text"], Understanding(**state["understanding"]))
        out = wo.model_dump()
        t.done(out)
    return {"work_order": out}


def node_classify(state: CaseState) -> dict:
    from app.schemas.models import Classification, WorkOrder

    with _trace(state.get("case_id"), "classify", {
        "raw_text": state.get("raw_text", ""),
        "work_order": state.get("work_order"),
    }) as t:
        wo = WorkOrder(**state["work_order"])
        cls = classify.run(wo, state["raw_text"], vision_signals=state.get("vision_signals"))
        out = cls.model_dump()
        t.done(out)
    return {"classification": out}


def node_route(state: CaseState) -> dict:
    from app.schemas.models import Classification, Understanding, WorkOrder
    from app.services import urgency as urgency_svc

    with _trace(state.get("case_id"), "route", {
        "raw_text": state.get("raw_text", ""),
        "work_order": state.get("work_order"),
        "classification": state.get("classification"),
    }) as t:
        wo = WorkOrder(**state["work_order"])
        cls = Classification(**state["classification"])
        routing = route.run(wo, cls, state["raw_text"], vision_signals=state.get("vision_signals"))
        # 支柱二：急件识别与办理时限分级（规则式 + 图片证据升级，随转派节点产出）
        und = Understanding(**state["understanding"]) if state.get("understanding") else None
        urg = urgency_svc.assess(state["raw_text"], und, wo, cls, vision_signals=state.get("vision_signals"))
        out = routing.model_dump()
        t.done({**out, "urgency": urg})
    return {"routing": out, "urgency": urg}


def node_reply(state: CaseState) -> dict:
    from app.schemas.models import Classification, ReplyDraft, Routing, WorkOrder

    with _trace(state.get("case_id"), "reply", {
        "raw_text": state.get("raw_text", ""),
        "work_order": state.get("work_order"),
        "classification": state.get("classification"),
        "routing": state.get("routing"),
    }) as t:
        wo = WorkOrder(**state["work_order"])
        cls = Classification(**state["classification"])
        rt = Routing(**state["routing"])
        draft = reply.run(wo, cls, rt, state["raw_text"])
        out = draft.model_dump()
        t.done(out)
    return {"reply_draft": out}


def node_review_gate(state: CaseState) -> dict:
    """人工审核中断点：interrupt 挂起；API resume 后以工作人员意见放行。"""
    human_input = interrupt(
        {
            "stage": "awaiting_review",
            "message": "全链路建议已生成，等待工作人员审核确认",
            "sections": ["work_order", "classification", "routing", "reply"],
        }
    )
    note = ""
    if isinstance(human_input, dict):
        note = str(human_input.get("note", "")).strip()
    elif human_input is not None:
        note = str(human_input).strip()
    return {"status": "completed", "review_note": note}


def node_finalize(state: CaseState) -> dict:
    logger.info("case %s finalized at %s", state.get("case_id"), _now())
    return {"status": "completed"}


# 说明：needs_clarification 不中断链路——缺失信息作为"待问市民的问题"随结果展示，
# 工作人员可补充信息后重跑（/clarify）或直接基于现有最佳建议审核。


# ---------------- 图构建（进程内单例） ----------------

_graph: Any = None
_conn: sqlite3.Connection | None = None


def get_graph() -> Any:
    global _graph, _conn
    if _graph is not None:
        return _graph

    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    tracing.init(settings.storage_dir)
    _conn = sqlite3.connect(str(settings.storage_dir / "checkpoints.sqlite3"), check_same_thread=False)

    graph = StateGraph(CaseState)
    graph.add_node("understand", node_understand)
    graph.add_node("work_order", node_work_order)
    graph.add_node("classify", node_classify)
    graph.add_node("route", node_route)
    graph.add_node("reply", node_reply)
    graph.add_node("review_gate", node_review_gate)
    graph.add_node("finalize", node_finalize)

    graph.set_entry_point("understand")
    graph.add_edge("understand", "work_order")
    graph.add_edge("work_order", "classify")
    graph.add_edge("classify", "route")
    graph.add_edge("route", "reply")
    graph.add_edge("reply", "review_gate")
    graph.add_edge("review_gate", "finalize")
    graph.add_edge("finalize", END)

    _graph = graph.compile(checkpointer=SqliteSaver(_conn))
    return _graph


def run_chain(
    case_id: str,
    raw_text: str,
    source_channel: str = "直接来电（呼入）",
    clarification_context: list[str] | None = None,
    vision_signals: list[dict] | None = None,
) -> dict:
    """跑完整链路，停在人工审核中断点（或 needs_clarification / failed）。

    vision_signals：图片证据的视觉结论，注入分类/派单提示词并用于急件分级升级。
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": case_id}}
    initial: CaseState = {
        "case_id": case_id,
        "raw_text": raw_text,
        "source_channel": source_channel,
        "clarification_context": clarification_context or [],
        "vision_signals": vision_signals or None,
        "status": "processing",
        "error": None,
    }
    try:
        graph.invoke(initial, config)
    except Exception as exc:  # noqa: BLE001 - 业务失败需落库
        logger.exception("workflow failed for case %s", case_id)
        return {"status": "failed", "error": str(exc), "case_id": case_id}
    snapshot = graph.get_state(config)
    values = dict(snapshot.values)
    if snapshot.next:  # 中断在 review_gate
        values["status"] = "awaiting_review"
    values.setdefault("status", "completed")
    values["case_id"] = case_id
    return values

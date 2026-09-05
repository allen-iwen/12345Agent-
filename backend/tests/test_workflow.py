"""工作流离线集成测试：用桩 LLM 跑完整链路，无需真实 API。"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from langgraph.types import Command

from app.agents import classify, reply, route, understand, work_order
from app.workflow import graph as workflow_graph

# 5 个节点按 understand → work_order → classify → route → reply 顺序各被调用一次
STUBS: list[dict] = [
    # 1) 诉求理解
    {
        "summary": "群众反映公交站被社会车辆长期占用",
        "elements": {"requester": "某市民", "contact": "待确认", "location": "市区", "time": "长期", "event": "社会车辆占用公交站"},
        "urgent": False,
        "repeat_request": False,
        "needs_clarification": True,
        "missing_fields": ["具体哪个区/哪条路", "公交站名称"],
        "manual_action": None,
    },
    # 2) 标准化工单
    {
        "title": "关于市区公交站被社会车辆长期占用的问题",
        "region": "市本级",
        "requester": "匿名市民",
        "contact": "待确认",
        "location": "市区某公交站（待确认）",
        "occurrence_time": "长期",
        "event_description": "社会车辆长期占用公交站，导致公交车无法正常进站。",
        "handling_request": "请求相关部门核查处理并答复。",
    },
    # 3) 事项分类
    {
        "category_code": "transportation",
        "category_name": "交通运输",
        "confidence": 0.93,
        "reason": "诉求主体是公交站被占用，归属交通运输类。",
        "candidates": [
            {"code": "transportation", "name": "交通运输", "score": 0.93, "reason": "涉及公交站秩序"},
            {"code": "public_safety", "name": "公共安全", "score": 0.05, "reason": "无明显公共安全隐患"},
        ],
    },
    # 4) 承办单位推荐
    {
        "departments": [
            {"name": "芜湖公交公司", "role": "建议承办单位", "reason": "公交站运营主体"},
            {"name": "市公安局", "role": "协办单位", "reason": "现场交通秩序管理"},
        ],
        "primary": "芜湖公交公司",
        "note": "依据历史工单参考。",
    },
    # 5) 答复建议
    {
        "reply_text": "尊敬的市民：您好！您反映的「市区公交站被社会车辆长期占用」问题已收悉……",
        "tone": "正式、耐心、规范",
        "disclaimer": "本回复由智能体草拟，发送前须经工作人员审核确认。",
    },
]


class _StubQueue:
    def __init__(self, items: list[dict]) -> None:
        self.items = list(items)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str, **kwargs: Any) -> dict:
        self.calls.append((system[:40], user[:40]))
        if not self.items:
            raise AssertionError("stub 用尽")
        return self.items.pop(0)


@pytest.fixture
def stub_llm(monkeypatch: pytest.MonkeyPatch) -> _StubQueue:
    queue = _StubQueue([dict(s) for s in STUBS])
    for mod in (understand, work_order, classify, route, reply):
        monkeypatch.setattr(mod, "chat_json", queue)
    return queue


def test_full_chain_stops_for_human_review(stub_llm: _StubQueue) -> None:
    case_id = f"test-{uuid.uuid4().hex[:8]}"
    values = workflow_graph.run_chain(
        case_id,
        "市区一处公交站被社会车辆长期占用，公交车无法正常进站。",
    )
    assert values["status"] == "awaiting_review", values
    assert stub_llm.items == [], f"剩余未用 stub：{stub_llm.items}"
    assert values["understanding"]["summary"] == "群众反映公交站被社会车辆长期占用"
    assert values["understanding"]["needs_clarification"] is True
    assert values["understanding"]["missing_fields"] == ["具体哪个区/哪条路", "公交站名称"]
    assert values["work_order"]["title"].startswith("关于市区公交站")
    assert values["classification"]["category_code"] == "transportation"
    assert values["classification"]["confidence"] == pytest.approx(0.93)
    assert values["routing"]["primary"] == "芜湖公交公司"
    assert {d["name"] for d in values["routing"]["departments"]} >= {"芜湖公交公司", "市公安局"}
    assert "尊敬的市民" in values["reply_draft"]["reply_text"]


def test_final_resume_completes_case(stub_llm: _StubQueue) -> None:
    case_id = f"test-final-{uuid.uuid4().hex[:8]}"
    values = workflow_graph.run_chain(case_id, "测试诉求文本，要求处理路灯不亮问题。")
    assert values["status"] == "awaiting_review"

    g = workflow_graph.get_graph()
    cfg = {"configurable": {"thread_id": case_id}}
    g.invoke(Command(resume={"note": "审核通过"}), cfg)
    snapshot = g.get_state(cfg)
    # LangGraph 在最终态返回空元组 next=()
    assert not snapshot.next
    final_values = dict(snapshot.values)
    assert final_values["status"] == "completed"
    assert final_values["review_note"] == "审核通过"

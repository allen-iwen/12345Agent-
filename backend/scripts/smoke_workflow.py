"""端到端链路测试：直接调 run_chain（真实 DeepSeek 调用）。"""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workflow.graph import run_chain  # noqa: E402

CASES = [
    ("mock-004", "市区一处公交站被社会车辆长期占用，公交车无法正常进站。"),
    ("mock-001", "南陵县某理发店没有公示服务价格，也没有在醒目位置悬挂营业执照，希望有关部门核查。"),
    ("mock-006", "现在闻到楼道内有很重的燃气味，疑似发生泄漏，请立即处理。"),
]


def main() -> None:
    out = []
    for tag, text in CASES:
        case_id = f"smoke-{tag}-{uuid.uuid4().hex[:6]}"
        print(f"\n===== {tag} {case_id} =====")
        values = run_chain(case_id, text)
        print("status:", values.get("status"))
        if values.get("error"):
            print("ERROR:", values["error"])
        u = values.get("understanding") or {}
        print("understanding:", json.dumps(
            {k: u.get(k) for k in ("summary", "urgent", "repeat_request", "needs_clarification", "missing_fields", "manual_action")},
            ensure_ascii=False))
        wo = values.get("work_order") or {}
        print("work_order.title:", wo.get("title"))
        cls = values.get("classification") or {}
        print("classification:", cls.get("category_code"), cls.get("category_name"), cls.get("confidence"))
        rt = values.get("routing") or {}
        print("routing.primary:", rt.get("primary"), [d.get("name") for d in rt.get("departments", [])])
        rd = values.get("reply_draft") or {}
        reply = rd.get("reply_text", "")
        print("reply_text[:120]:", reply[:120].replace("\n", " "))
        out.append({
            "tag": tag,
            "status": values.get("status"),
            "category": cls.get("category_code"),
            "urgent": u.get("urgent"),
            "repeat": u.get("repeat_request"),
            "clarify": u.get("needs_clarification"),
        })
    print("\n===== SUMMARY =====")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

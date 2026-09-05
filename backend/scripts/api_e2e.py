"""API 级端到端测试：创建案件 → 分节审核 → 最终放行。"""
import json
import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:8000"
# trust_env=False：不走系统代理，直连本机
client = httpx.Client(timeout=180, trust_env=False)


def wait_health() -> None:
    for _ in range(30):
        try:
            if client.get(BASE + "/health").json().get("status") == "ok":
                return
        except Exception:
            pass
        time.sleep(1)
    raise SystemExit("backend not up")


def main() -> None:
    wait_health()
    text = "市区一处公交站被社会车辆长期占用，公交车无法正常进站。"
    print("POST /api/cases ...")
    case = client.post(BASE + "/api/cases", json={"text": text, "source_channel": "直接来电（呼入）"}).json()
    print("case_id:", case["case_id"], "status:", case["status"])
    assert case["status"] == "awaiting_review", case["status"]
    print("title:", case["work_order"]["title"])
    print("category:", case["classification"]["category_code"], case["classification"]["category_name"],
          "conf=", case["classification"]["confidence"])
    print("primary dept:", case["routing"]["primary"])
    print("departments:", [d["name"] for d in case["routing"]["departments"]])
    print("reply head:", case["reply_draft"]["reply_text"][:80].replace("\n", " "))
    print("missing_fields:", case["understanding"]["missing_fields"])

    # 分节审核：全部 approve
    for section in ("work_order", "classification", "routing", "reply"):
        r = client.post(f"{BASE}/api/cases/{case['case_id']}/review",
                        json={"section": section, "action": "approve"})
        r.raise_for_status()
        print(f"review {section} ->", r.json()["review"][section])

    # 修正演示：先 modify 工单标题再 approve（验证 modify 通道）
    r = client.post(f"{BASE}/api/cases/{case['case_id']}/review", json={
        "section": "work_order", "action": "modify",
        "payload": {**case["work_order"], "title": "关于市区一处公交站被社会车辆占用的问题"},
        "note": "标题微调",
    })
    r.raise_for_status()
    print("modify work_order ->", r.json()["review"]["work_order"], r.json()["work_order"]["title"])

    # 最终放行（resume 工作流）
    r = client.post(f"{BASE}/api/cases/{case['case_id']}/review",
                    json={"section": "final", "action": "approve", "note": "审核通过"})
    r.raise_for_status()
    final = r.json()
    print("final status:", final["status"], "completed_at:", final["completed_at"])
    assert final["status"] == "completed"

    # 列表验证
    lst = client.get(BASE + "/api/cases").json()
    print("case list:", [(c["case_id"][:8], c["status"]) for c in lst[:5]])
    print("\nAPI E2E PASSED")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""全链路 E2E：创建 → 检查 runs 轨迹落库 → 审核 → 放行 → 知识库接口。"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    # 1. 健康检查
    assert call("GET", "/health")["status"] == "ok"

    # 2. 创建案件（真实 LLM 全链路）
    print("POST /api/cases ...")
    c = call("POST", "/api/cases", {"text": "南陵县许镇镇某理发店未公示服务价格，也没有悬挂营业执照，请核查处理。", "source_channel": "直接来电（呼入）"})
    cid = c["case_id"]
    print("case:", cid[:8], "status:", c["status"])
    assert c["status"] == "awaiting_review", c.get("error")

    # 3. 轨迹落库检查（5 节点全记录）
    runs = call("GET", f"/api/runs/cases/{cid}")["runs"]
    nodes = [r["node"] for r in runs]
    print("runs nodes:", nodes)
    for expect in ("understand", "work_order", "classify", "route", "reply"):
        assert expect in nodes, f"缺节点 {expect}"
    for r in runs:
        assert r["status"] == "ok", (r["node"], r["error"])
        assert r["output_json"], r["node"]
    print("trace OK: 5/5 节点，输出全部落库")

    # 4. 知识库接口
    cats = call("GET", "/api/knowledge/categories")
    n_cat = len(cats.get("categories", []))
    orders = call("GET", "/api/knowledge/orders")
    similar = call("GET", "/api/knowledge/search?text=" + urllib.request.quote("理发店没有公示价格") + "&top_k=3")
    top = similar["hits"][0]
    print(f"knowledge OK: {n_cat} 类别 / {orders['total']} 工单 / 相似检索 top1: {top['category']} {top['title'][:22]}")
    assert n_cat == 12 and orders["total"] == 18

    # 5. 分节审核 + 最终放行
    for sec in ("work_order", "classification", "routing", "reply"):
        c = call("POST", f"/api/cases/{cid}/review", {"section": sec, "action": "approve"})
        assert c["review"][sec] == "approved"
    c = call("POST", f"/api/cases/{cid}/review", {"section": "final", "action": "approve", "note": "E2E 通过"})
    print("final:", c["status"], c["completed_at"])
    assert c["status"] == "completed"

    print("\nE2E PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

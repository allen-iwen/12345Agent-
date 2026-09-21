# -*- coding: utf-8 -*-
"""流转状态机验证：状态定义、合法/非法迁移、角色守卫、看板与历史。

不依赖 LLM：服务级校验 + 真实 API 调用（复用既有案件）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from app.services import workflow_state as ws  # noqa: E402

BASE = "http://127.0.0.1:8000"
FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAIL.append(name)


def main() -> int:
    print("=== 1. 状态机定义（服务级）===")
    check("状态齐全（主线 8 + 旁路 2）", len(ws.STATES) == 10, f"{len(ws.STATES)} 个")
    ok, _ = ws.can_transition("triaged", "dispatched", "dispatcher")
    check("派单员可派单", ok)
    ok, reason = ws.can_transition("triaged", "dispatched", "agent")
    check("坐席无权派单（角色守卫）", not ok, reason[:40])
    ok, reason = ws.can_transition("received", "closed", "admin")
    check("跳步迁移被拒", not ok, reason[:40])
    ok, _ = ws.can_transition("received", "triaged", "system")
    check("系统可自动推进受理→已分类", ok)
    actions = ws.next_actions("dispatched", "dept")
    check("部门用户可见签收/退回动作",
          any(a["to"] == "accepted" and a["allowed"] for a in actions),
          "、".join(a["action"] for a in actions))

    print("\n=== 2. 状态与迁移定义接口 ===")
    st = requests.get(f"{BASE}/api/flow/states", timeout=15).json()
    check("接口返回状态与迁移", len(st["states"]) == 10 and len(st["transitions"]) >= 12,
          f"{len(st['states'])} 状态 / {len(st['transitions'])} 迁移")

    print("\n=== 3. 看板 ===")
    board = requests.get(f"{BASE}/api/flow/board", timeout=30).json()
    print(f"  案件总数 {board['total_cases']}｜列出 {board['listed']}｜分布 {board['counts']}")
    check("看板返回全部分组", len(board["groups"]) == 10, f"{len(board['groups'])} 组")
    check("看板案件含时限状态", all("deadline_state" in it for g in board["groups"] for it in g["items"]))
    check("历史案件默认已受理", board["counts"].get("received", 0) > 0, str(board["counts"].get("received")))

    print("\n=== 4. 迁移与历史（真实调用）===")
    target = next((it for g in board["groups"] if g["state"] == "received" for it in g["items"]), None)
    if target is None:
        print("  无已受理案件，跳过")
        return 1
    cid = target["case_id"]
    flow = requests.get(f"{BASE}/api/cases/{cid}/flow", timeout=15).json()
    check("案件流转查询可用", flow["flow_state"] == "received" and flow["flow_label"] == "已受理")
    check("流转历史为列表", isinstance(flow["history"], list), f"{len(flow['history'])} 条")

    r = requests.post(f"{BASE}/api/cases/{cid}/transition",
                      json={"to": "closed", "actor": "测试员", "role": "admin"}, timeout=20)
    check("非法迁移返回 409", r.status_code == 409, str(r.json().get("detail", ""))[:48])

    requests.post(f"{BASE}/api/cases/{cid}/transition",
                  json={"to": "triaged", "actor": "系统", "role": "admin"}, timeout=20)
    r = requests.post(f"{BASE}/api/cases/{cid}/transition",
                      json={"to": "dispatched", "actor": "坐席A", "role": "agent"}, timeout=20)
    check("越权派单返回 409", r.status_code == 409, str(r.json().get("detail", ""))[:46])

    r = requests.post(f"{BASE}/api/cases/{cid}/transition",
                      json={"to": "dispatched", "note": "确认承办单位：属地政府",
                            "actor": "派单员B", "role": "dispatcher"}, timeout=20)
    ok_dispatch = r.status_code == 200 and r.json().get("to") == "dispatched"
    check("派单员派单成功", ok_dispatch,
          (r.json().get("to_label") or "") if r.status_code == 200 else str(r.status_code))

    flow2 = requests.get(f"{BASE}/api/cases/{cid}/flow", timeout=15).json()
    check("流转历史记录操作者与角色",
          any(h.get("actor") == "派单员B" and h.get("role") == "dispatcher" for h in flow2["history"]),
          f"{len(flow2['history'])} 条记录")

    chain = [("accepted", "dept"), ("processing", "dept"), ("replied", "dept"),
             ("reviewed", "reviewer"), ("closed", "reviewer")]
    all_ok = True
    for to, role in chain:
        rr = requests.post(f"{BASE}/api/cases/{cid}/transition",
                           json={"to": to, "actor": f"{role}-用户", "role": role}, timeout=20)
        if rr.status_code != 200:
            all_ok = False
            print(f"    迁移 {to} 失败：{rr.status_code} {str(rr.json().get('detail', ''))[:60]}")
    check("主线全链路迁移（签收→办理→回执→审核→归档）", all_ok)

    flow3 = requests.get(f"{BASE}/api/cases/{cid}/flow", timeout=15).json()
    check("最终状态为已归档", flow3["flow_state"] == "closed", flow3["flow_label"])
    check("流转记录完整（≥7 条）", len(flow3["history"]) >= 7, f"{len(flow3['history'])} 条")

    print("\n流转状态机验证：" + ("PASS" if not FAIL else "FAIL：" + "；".join(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

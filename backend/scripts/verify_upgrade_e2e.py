# -*- coding: utf-8 -*-
"""阶段A端到端验证：答复合规审查与时限倒计时随案件返回 + 临期/超期清单。"""
import sys

import requests

BASE = "http://127.0.0.1:8000"
FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAIL.append(name)


def main() -> int:
    cases = requests.get(f"{BASE}/api/cases?limit=30", timeout=20).json()
    print(f"案件数：{len(cases)}")

    # 1) 答复合规审查（取有答复的案件）
    target = next((c for c in cases if c.get("reply_draft") and c.get("status") == "awaiting_review"), None)
    if target is None:
        print("未找到含答复的案件")
        return 1
    detail = requests.get(f"{BASE}/api/cases/{target['case_id']}", timeout=20).json()
    ra = detail.get("reply_audit") or {}
    print(f"\n=== 答复合规审查（{target['case_id'][:10]}）===")
    print(f"  风险等级：{ra.get('risk_level')}｜检查规则 {ra.get('checked_rules')} 条")
    for f in (ra.get("findings") or [])[:3]:
        print(f"    - [{f['severity']}] {f['label']}：{f['quote'][:30]} → {f['suggestion'][:36]}")
    print(f"  依据：{(ra.get('basis') or {}).get('name', '')}")
    check("案件返回 reply_audit", bool(ra))
    check("含风险等级", ra.get("risk_level") in ("高", "中", "低", "无"), str(ra.get("risk_level")))
    check("含政策依据条款", bool((ra.get("basis") or {}).get("clause")))

    # 2) 时限倒计时
    dl = detail.get("deadline") or {}
    print(f"\n=== 时限倒计时 ===")
    print(f"  等级 {dl.get('level')}｜{dl.get('label')}")
    print(f"  到期 {dl.get('due_at')}（{dl.get('mode')}）｜剩余 {dl.get('remaining_hours')}h｜状态 {dl.get('state')}")
    print(f"  依据：{(dl.get('basis') or {}).get('clause', '')[:44]}")
    if dl.get("notes"):
        print(f"  标注：{'；'.join(dl['notes'])}")
    check("案件返回 deadline", bool(dl))
    check("含到期时刻与状态", bool(dl.get("due_at")) and dl.get("state") in ("正常", "临期", "超期", "已办结"))
    check("含依据条款", bool((dl.get("basis") or {}).get("clause")))

    # 3) 临期/超期清单
    print(f"\n=== 临期/超期清单 ===")
    rows = requests.get(f"{BASE}/api/cases/deadlines", params={"window_hours": 24}, timeout=20).json()
    overdue = [r for r in rows if r["state"] == "超期"]
    near = [r for r in rows if r["state"] == "临期"]
    print(f"  共 {len(rows)} 条｜超期 {len(overdue)}｜临期 {len(near)}")
    for r in rows[:4]:
        print(f"    [{r['state']}] {r['title'][:26]}｜到期 {r['due_at']}｜剩 {r['remaining_hours']}h")
    check("清单接口可用", isinstance(rows, list))
    check("能识别超期案件（历史案件）", len(overdue) > 0, f"{len(overdue)} 条")
    if rows:
        check("清单含督办建议", bool(rows[0].get("supervision")))

    print("\n阶段A端到端：" + ("PASS" if not FAIL else "FAIL：" + "；".join(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

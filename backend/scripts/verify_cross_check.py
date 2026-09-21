# -*- coding: utf-8 -*-
"""第二模型交叉复核验证：复核调用、分歧记录、统计口径。

做法：临时以 case 级开关验证——直接调用 review 服务与统计接口，
再由统计接口核对真实案件中的复核记录（不伪造数据）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from app.schemas.models import WorkOrder  # noqa: E402
from app.services import review  # noqa: E402

BASE = "http://127.0.0.1:8000"
FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAIL.append(name)


def main() -> int:
    st = review.status()
    print("=== 复核配置 ===")
    print(f"  enabled={st['enabled']}｜model={st['model']}｜base_url={st['base_url']}")
    print(f"  提示：{st['note']}")

    print("\n=== 复核调用（服务级，直接问第二模型）===")
    wo = WorkOrder(
        title="关于某小区北门烧烤店占道经营及油烟噪音扰民的问题",
        region="芜湖市鸠江区", location="鸠江区某小区北门",
        event_description="烧烤店每晚占道摆桌经营，油烟直排入户，噪音至凌晨两点，多次反映未解决。",
        handling_request="依法整治占道经营与油烟噪音",
    )
    sec = review.classify_second_opinion(wo, wo.event_description)
    if not st["enabled"]:
        check("未启用时优雅返回不可用", sec.get("available") is False, str(sec.get("note"))[:48])
        print("  （如需完整验证：.env 设 LLM_REVIEW_ENABLED=true 后重启）")
    else:
        check("复核模型返回结论", sec.get("available") is True and bool(sec.get("category_code")),
              f"{sec.get('category_name')}（{sec.get('confidence')}）")
        print(f"  复核结论：{sec.get('category_name')}｜理由：{(sec.get('reason') or '')[:50]}")

        print("\n=== 分歧比较 ===")
        same = review.compare(sec.get("category_code"), sec)
        check("与自身比较应一致", same.get("agreement") is True, str(same.get("agreement")))
        diff = review.compare("health", sec)
        check("不同结论判为分歧", diff.get("agreement") is False, str(diff.get("note"))[:44])
        print(f"  分歧说明：{diff.get('note')}")
        check("分歧含双方结论与模型名", bool(diff.get("primary_choice")) and bool(diff.get("secondary_model")))

    print("\n=== 统计接口 ===")
    r = requests.get(f"{BASE}/api/stats/review", timeout=30)
    check("复核统计接口可用", r.status_code == 200, str(r.status_code))
    if r.status_code == 200:
        d = r.json()
        print(f"  已复核案件 {d['checked_cases']}｜一致 {d['agreed']}｜分歧 {d['diverged']}"
              f"｜一致率 {d['agreement_rate']}｜人工介入率 {d['human_gate_rate']}")
        check("统计含配置与样本", "config" in d and "checked_cases" in d)
        check("统计口径自洽（一致+分歧=已复核）", d["agreed"] + d["diverged"] == d["checked_cases"])

    d2 = requests.get(f"{BASE}/api/stats/deadlines", timeout=30)
    check("时限督办统计可用", d2.status_code == 200)
    if d2.status_code == 200:
        dd = d2.json()
        print(f"  时限分布：{dd['buckets']}｜最紧迫 {len(dd['urgent'])} 件")
        check("时限分布含四类状态", set(dd["buckets"]) >= {"正常", "临期", "超期", "已办结"})

    print(f"\n交叉复核验证：{len(FAIL) == 0 and 'PASS' or 'FAIL：' + '；'.join(FAIL)}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""端到端验证：真实链路建单，检查三支柱字段是否随案件返回。"""
import sys
import time

import requests

BASE = "http://127.0.0.1:8000"

CASES = [
    ("城市管理·职责交叉", "我是鸠江区棠梅小区的住户，小区北门外的兄弟烧烤店每天晚上占道摆桌，油烟直接飘进家里，"
                          "一直到凌晨两点多特别吵，跟物业反映过没人管，而且我已经多次反映仍未解决。请相关部门尽快处理。",
     {"dispatch_path": "属地主办", "primary_contains": "鸠江区政府", "urgency": "一般",
      "needs_human": True, "governance_repeat": True, "max_departments": 4}),
    ("公共安全·安全隐患", "镜湖区某小区门口燃气管道破裂，能闻到很浓的燃气味，旁边就是居民楼，非常危险，请马上派人处理！",
     {"dispatch_path": "属地主办", "primary_contains": "镜湖区政府", "urgency": "特急",
      "needs_human": True, "governance_repeat": False, "max_departments": 4}),
]


def main() -> int:
    fails = []
    for label, text, expect in CASES:
        print(f"\n=== {label} ===")
        r = requests.post(f"{BASE}/api/cases", json={"text": text}, timeout=900)
        if r.status_code != 200:
            print("  建单失败:", r.status_code, r.text[:200])
            fails.append(label + ":建单")
            continue
        c = r.json()
        cid = c["case_id"]
        rt = c.get("routing") or {}
        urg = c.get("urgency") or {}
        gov = c.get("governance") or {}
        co = [d for d in rt.get("departments", []) if d["role"] != "建议承办单位"]

        print(f"  案件 {cid[:10]}｜状态 {c['status']}")
        print(f"  分类：{c['classification']['category_name']}（{c['classification']['confidence']}）")
        print(f"  主办：{rt.get('primary')}（{rt.get('primary_kind')}）｜路径：{rt.get('dispatch_path')}")
        print(f"  协办 {len(co)} 家：{[(d['name'], d['role']) for d in co]}")
        print(f"  依据链 {len(rt.get('evidence_chain') or [])} 条：" + " / ".join(
            f"{e['type']}" for e in (rt.get("evidence_chain") or [])))
        print(f"  规则-模型一致：{rt.get('rule_llm_agreement')}｜需人工判断：{rt.get('needs_human_judgment')}")
        print(f"  人工提示：{(rt.get('judgment_note') or '无')[:60]}")
        print(f"  退回风险：{(rt.get('return_risk') or '无')[:50]}")
        print(f"  急件分级：{urg.get('level')}｜{urg.get('limit_hint', '')[:40]}")
        print(f"  治理：并案={bool(gov.get('aggregation'))} 重复={bool(gov.get('repeat'))} "
              f"退回={bool(gov.get('return_risk'))}｜建议{len(gov.get('suggestions', []))}条")

        if not rt.get("evidence_chain"):
            fails.append(f"{label}:依据链为空")
        if rt.get("dispatch_path") != expect["dispatch_path"]:
            fails.append(f"{label}:路径={rt.get('dispatch_path')}≠{expect['dispatch_path']}")
        if expect["primary_contains"] not in (rt.get("primary") or ""):
            fails.append(f"{label}:主办={rt.get('primary')}≠含{expect['primary_contains']}")
        if urg.get("level") != expect["urgency"]:
            fails.append(f"{label}:急件={urg.get('level')}≠{expect['urgency']}")
        if bool(rt.get("needs_human_judgment")) != expect["needs_human"]:
            fails.append(f"{label}:需人工判断={rt.get('needs_human_judgment')}")
        if bool(gov.get("repeat")) != expect["governance_repeat"]:
            fails.append(f"{label}:重复诉求={bool(gov.get('repeat'))}")
        if len(co) > expect["max_departments"]:
            fails.append(f"{label}:协办未去重({len(co)}家)")

    print("\n=== 断言 ===")
    print("  三支柱端到端：" + ("PASS（全部断言通过）" if not fails else "FAIL：" + "；".join(fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())

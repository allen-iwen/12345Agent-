# -*- coding: utf-8 -*-
"""判别实验：laya 在中文上的低表现，是「CPU 部署」还是「跨语言/领域迁移」？

设计（控制变量）：
  配置 A：中文 state + 中文选项       —— 与既有评测一致（基线 22.2%）
  配置 B：英文 state + 英文选项       —— 若显著更高 → 跨语言迁移是主因
  配置 C：中文 state + 英文选项       —— 分离「state 语言」与「选项语言」的影响
CPU/GPU 只影响延迟与数值精度（同一权重、同一前向计算），不可能造成 22% vs 100% 的差距；
若 B/C 明显优于 A，即可排除 CPU 因素，把原因定位到语言与领域分布。

用法：python scripts/probe_laya_language.py [--limit N]
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import decision  # noqa: E402
from app.services.llm import chat_json  # noqa: E402

# 英文选项（与 12 类 + 兜底一一对应，描述尽量短，避免 token 预算截断）
EN_CATALOG = {
    "urban_management": "Urban management & city appearance: illegal vending/street stalls, illegal construction, garbage clearing, outdoor ads, restaurant fumes",
    "ecology_environment": "Ecology & environment: industrial pollution, wastewater, hazardous waste, production-source noise/air pollution",
    "market_regulation": "Market regulation: product quality, unlicensed business, false advertising, consumer disputes, merchant refunds",
    "transportation": "Transportation: bus routes/stops, taxis, ride-hailing, traffic signals, road transport, parking",
    "urban_rural_construction": "Urban & rural construction: road construction/repair, construction sites, housing quality, demolition & resettlement, property management",
    "public_service": "Public services: water/gas/electricity supply, telecom & internet, public transport service quality, civil affairs",
    "public_safety": "Public safety: fire safety, fire hydrants, public security, workplace safety, immediate hazards",
    "labor_social_security": "Labor & social security: unpaid wages, labor contracts, work injury, social insurance, employment",
    "health": "Health: hospitals, clinics, medical aesthetics, vaccination, public health services",
    "science_education_culture_sports": "Education, culture & sports: schools, enrollment, tutoring refunds, cultural venues, tourism",
    "agriculture_forestry_water_land": "Agriculture, forestry, water & land: farmland, land contracting, homestead approval, land requisition, irrigation",
    "economic_trade": "Economy & trade: banking, loans, insurance, investment, taxation, business operations",
    "other": "None of the above, or not enough information",
}

TRANSLATE_SYSTEM = """你是专业翻译。把给定的中文政务工单条目翻译成英文，用于跨语言分类实验。
要求：忠于原意、保留地名与机构名的拼音或意译（如 镜湖区 → Jinghu District），不要解释、不要增删信息。
输出 JSON：{"items": [{"id": <原样返回>, "title_en": "...", "request_en": "..."}]}"""


def translate(rows: list[dict]) -> dict[int, dict]:
    """分批翻译（每批 6 条，控制单次输出长度）。"""
    out: dict[int, dict] = {}
    for i in range(0, len(rows), 6):
        batch = [{"id": i + j, "title": r["title"], "request": r["request_content"][:400]}
                 for j, r in enumerate(rows[i:i + 6])]
        data = chat_json(TRANSLATE_SYSTEM, "条目：\n" + json.dumps(batch, ensure_ascii=False),
                         temperature=0.0, max_tokens=8000)
        for it in data.get("items", []):
            try:
                out[int(it["id"])] = {"title_en": str(it.get("title_en", "")),
                                      "request_en": str(it.get("request_en", ""))}
            except (KeyError, TypeError, ValueError):
                continue
    return out


def ask_once(state: dict, criteria: dict[str, str]) -> dict:
    q = {"category": decision.choice(
        "Which category is the core issue of this citizen complaint? Judge by the core issue, not by location.",
        criteria)}
    return decision.ask(state, q)


def eval_conf(rows: list[dict], translations: dict[int, dict], mode: str) -> tuple[int, float, list[tuple[str, str]]]:
    """mode: zh_zh | en_en | zh_en"""
    options = EN_CATALOG if mode != "zh_zh" else {c["code"]: c["name"] for c in
                                                  json.loads((Path("data/categories/category_catalog.json")
                                                              .read_text(encoding="utf-8")))["categories"]}
    if mode == "zh_zh":
        from app.services import decision_case
        options = decision_case.category_criteria()
    hits, lat, errors = 0, [], []
    for i, r in enumerate(rows):
        tr = translations.get(i)
        if mode.startswith("en") and not tr:
            continue
        state = ({"complaint": f"{tr['title_en']}. {tr['request_en']}"} if mode.startswith("en")
                 else {"诉求原文": r["request_content"][:600], "工单标题": r["title"]})
        t0 = time.monotonic()
        res = ask_once(state, options)
        lat.append((time.monotonic() - t0) * 1000)
        if not res.get("available"):
            continue
        code = (res["answers"].get("category") or {}).get("value")
        gold = {c["name"]: c["code"] for c in json.loads(
            Path("data/categories/category_catalog.json").read_text(encoding="utf-8"))["categories"]}[r["category"]]
        ok = code == gold
        hits += ok
        if not ok:
            errors.append((r["category"], f"{code}"))
    n = len(lat)
    return hits, (sum(lat) / n if n else 0.0), errors


def main() -> int:
    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    rows = [json.loads(l) for l in Path("data/processed/work_orders.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    if limit:
        rows = rows[:limit]

    st = decision.status()
    print("=== 决策模型 ===")
    print(f"  provider={st['provider']} available={st['available']}")
    if not st["available"]:
        return 2

    print(f"\n=== 步骤 1：把 {len(rows)} 条官方样例译成英文（一次 LLM 调用/6 条）===")
    tr = translate(rows)
    print(f"  成功 {len(tr)}/{len(rows)}")

    print("\n=== 步骤 2：三种配置对比（同一批样本、同一模型、同一设备=CPU）===")
    results = {}
    for mode, label in [("zh_zh", "A 中文state + 中文选项"), ("en_en", "B 英文state + 英文选项"),
                        ("zh_en", "C 中文state + 英文选项")]:
        hits, avg, errors = eval_conf(rows, tr, mode)
        results[mode] = {"hits": hits, "avg_ms": round(avg, 1), "errors": errors[:6]}
        print(f"  {label}: {hits}/{len(rows)} = {hits / len(rows):.1%}｜平均 {avg:.0f}ms")
        if errors:
            print(f"      错例（真→预测）: " + "；".join(f"{g}→{p}" for g, p in errors[:4]))

    print("\n=== 结论判定 ===")
    a = results["zh_zh"]["hits"] / len(rows)
    b = results["en_en"]["hits"] / len(rows)
    c = results["zh_en"]["hits"] / len(rows)
    print(f"  A(中/中)={a:.1%}　B(英/英)={b:.1%}　C(中/英)={c:.1%}")
    if b > a + 0.15:
        print("  → 英文显著优于中文：**主因是跨语言迁移**，与 CPU 无关（同一权重、同一前向计算）")
    elif max(b, c) <= a + 0.15:
        print("  → 英文也未显著改善：**主因是该检查点在中文政务分类上的零样本能力不足**（领域+语言双重不匹配），"
              "与 CPU 无关")
    print("  说明：CPU 只影响延迟与数值精度，不改变学到的判定头；延迟差异见上表（同设备内可比）。")

    out = Path(f"data/eval/probe_laya_language{'_limit' + str(limit) if limit else ''}.json")
    out.write_text(json.dumps({"samples": len(rows), "device": "cpu", "results": results},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  结果已保存：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

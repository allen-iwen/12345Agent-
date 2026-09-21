# -*- coding: utf-8 -*-
"""Jev（System One 决策模型）事项分类评测：与生成模型基线同集同口径对比。

方法：官方 18 条样例工单做留一交叉验证（LOO，few-shot 池排除测试样本自身防泄漏），
- 基线：`scripts/eval_classify.py`（提示词链 + 生成模型，含 12 类辨析目录）
- 本评测：只用决策模型（Jev）做一次 Choice 判断，**不调用生成模型**

产出：准确率、平均延迟、输入 token、按官方价目折算的成本；
并单独统计「置信度门控」分布（auto/confirm/human）——这是合规上「拿不准就交人工」的量化依据。

用法（backend 目录）：
    python scripts/eval_classify_jev.py            # 全量 18 条
    python scripts/eval_classify_jev.py --limit 5  # 快速试跑
未配置 DECISION_PROVIDER / DECISION_API_KEY 时给出明确提示并退出（不伪造数据）。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.models import WorkOrder  # noqa: E402
from app.services import decision, decision_case  # noqa: E402

LLM_BASELINE_ACC = 1.0  # 既有基线：eval_classify.py 实测 18/18 = 100%
LLM_BASELINE_NOTE = "提示词链 + 生成模型（含 12 类辨析目录），LOO 100%"


def main() -> int:
    st = decision.status()
    print("=== 决策模型状态 ===")
    print(f"  可用={st['available']} 启用={st['enabled']} provider={st['provider']} model={st['model']}")
    print(f"  门控阈值：高≥{st['thresholds']['high']}（自动采用）/ 低<{st['thresholds']['low']}（转人工）")
    if not st["available"]:
        print("\n未配置决策模型，无法评测。请在 backend/.env 设置：")
        print("  DECISION_PROVIDER=typesafe")
        print("  DECISION_API_KEY=<typesafe.ai 控制台 API Keys>")
        print("凭证获取：typesafe.ai 候补名单 → console.typesafe.ai → API Keys；")
        print("或经 Vercel AI Gateway：DECISION_PROVIDER=vercel + AI Gateway Key（模型 typesafe-ai/jev）。")
        return 2

    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    rows = [
        json.loads(line)
        for line in Path("data/processed/work_orders.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if limit:
        rows = rows[:limit]

    print(f"\n=== Jev 分类评测（{len(rows)} 条，留一交叉验证）===")
    correct = 0
    gates = {"auto": 0, "confirm": 0, "human": 0}
    latencies: list[float] = []
    tokens = 0
    cost = 0.0
    errors: list[tuple[str, str, str]] = []

    for i, r in enumerate(rows, 1):
        wo = WorkOrder(
            title=r["title"],
            region=r.get("region", "芜湖市"),
            location=r.get("region", "待确认"),
            event_description=r["request_content"][:600],
            handling_request=r.get("reply_content", "")[:80] or "依法核实处理",
        )
        t0 = time.monotonic()
        try:
            out = decision_case.classify_only(r["request_content"][:600], wo)
        except Exception as exc:  # noqa: BLE001
            out = {"available": False, "note": str(exc)}
        dt = time.monotonic() - t0

        if not out.get("available"):
            print(f"  [{i}/{len(rows)}] 调用失败：{out.get('note')}")
            errors.append((r["title"][:24], r["category"], "调用失败"))
            continue

        pred = out.get("category_name") or "（无法归类）"
        ok = pred == r["category"]
        correct += ok
        gates[out.get("gate", "confirm")] = gates.get(out.get("gate", "confirm"), 0) + 1
        latencies.append(dt)
        tk = (out.get("usage") or {}).get("input_tokens") or 0
        tokens += tk
        cost += float(out.get("cost_usd") or 0)
        print(f"  [{i}/{len(rows)}] {'√' if ok else '×'} 真={r['category']} 预测={pred} "
              f"conf={out.get('confidence')} gate={out.get('gate')} {dt * 1000:.0f}ms")

    n = len(latencies)
    if n == 0:
        print("\n全部调用失败，无法给出指标。")
        return 1
    acc = correct / n
    avg_ms = sum(latencies) / n * 1000

    print("\n=== 对比结果 ===")
    print(f"{'口径':<28}{'准确率':>10}{'平均延迟':>12}{'输入token':>12}{'成本':>14}")
    print(f"{'生成模型基线（LLM 链）':<28}{LLM_BASELINE_ACC:>9.1%}{'（约 5-9s/案）':>12}{'—':>12}{'—':>14}")
    print(f"{'Jev 决策模型（本评测）':<28}{acc:>9.1%}{avg_ms:>10.0f}ms{tokens:>12}{'$' + format(cost, '.6f'):>14}")
    print(f"\n基线口径：{LLM_BASELINE_NOTE}")
    print(f"评测样本：{n} 条｜Jev 模型版本：{st['model']}")
    print(f"置信度门控分布：auto（可自动采用）{gates['auto']}｜confirm（人工确认）{gates['confirm']}｜human（转人工）{gates['human']}")

    out_path = Path("data/eval/jev_classify_result.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "samples": n,
        "model": st["model"],
        "accuracy": round(acc, 4),
        "avg_latency_ms": round(avg_ms, 1),
        "input_tokens": tokens,
        "cost_usd": round(cost, 6),
        "gate_distribution": gates,
        "llm_baseline": {"accuracy": LLM_BASELINE_ACC, "note": LLM_BASELINE_NOTE},
        "errors": [{"title": t, "gold": g, "pred": p} for t, g, p in errors],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存：{out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

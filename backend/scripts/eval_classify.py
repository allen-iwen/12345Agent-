# -*- coding: utf-8 -*-
"""分类准确率评测：官方历史工单留一交叉验证（LOO）。

对每条官方样例：用其余样例做 few-shot 参考，预测该条类别，与官方标签比对。
用法（backend 目录）：python scripts/eval_classify.py [--limit N]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.classify import run  # noqa: E402
from app.schemas.models import WorkOrder  # noqa: E402


def main() -> int:
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
    print(f"官方样例 {len(rows)} 条，留一交叉验证开始（每条约 10–30s）…", flush=True)

    correct, errors = 0, []
    t0 = time.time()
    for i, r in enumerate(rows):
        wo = WorkOrder(
            title=r["title"],
            region=r.get("region", "芜湖市"),
            location=r.get("region", "待确认"),
            event_description=r["request_content"][:600],
            handling_request=r.get("reply_content", "")[:80] or "依法核实处理",
        )
        try:
            pred = run(wo, r["request_content"][:600], exclude_source_ids=(r["source_id"],))
            pred_name = pred.category_name or "（无）"
        except Exception as exc:  # noqa: BLE001
            pred_name = f"异常:{exc}"
        ok = pred_name == r["category"]
        correct += ok
        mark = "√" if ok else "×"
        print(f"  [{i + 1}/{len(rows)}] {mark} 真={r['category']} 预测={pred_name} conf={pred.confidence:.2f} {r['title'][:24]}", flush=True)
        if not ok:
            errors.append((r["title"][:30], r["category"], pred_name))

    acc = correct / len(rows) if rows else 0.0
    print(f"\n===== LOO 分类准确率：{correct}/{len(rows)} = {acc:.1%}（{time.time() - t0:.0f}s）=====")
    if errors:
        print("错例：")
        for t, gold, pred in errors:
            print(f"  - {t}\n      真={gold} 预测={pred}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

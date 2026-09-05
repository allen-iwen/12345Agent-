# -*- coding: utf-8 -*-
"""本地实验模型全链路冒烟：用 vLLM 部署的 Qwen 跑一单完整链路。

用法（backend 目录）：
    python scripts/smoke_local_llm.py            # 默认 http://192.168.1.231:30001/v1
    python scripts/smoke_local_llm.py --base http://x:8000/v1 --model Qwen3.8-27B

通过环境变量覆盖 .env（DeepSeek 主配置不受影响），逐节点验证 5 个 Agent
产出完整。实验用途：token 不限、零成本调 prompt。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://192.168.1.231:30001/v1"
MODEL = "Qwen3.8-27B"

args = sys.argv[1:]
if "--base" in args:
    BASE = args[args.index("--base") + 1]
if "--model" in args:
    MODEL = args[args.index("--model") + 1]

# 环境变量优先于 .env（pydantic-settings），不改动主配置
os.environ["LLM_API_KEY"] = "EMPTY"
os.environ["LLM_BASE_URL"] = BASE
os.environ["LLM_MODEL"] = MODEL
os.environ["LLM_DISABLE_THINKING"] = "true"

from app.repositories import cases as repository  # noqa: E402
from app.workflow.graph import run_chain  # noqa: E402


def main() -> int:
    text = (
        "我是镜湖区棠梅小区的住户，楼下烧烤店每天晚上占道摆桌，油烟和噪音吵得没法睡觉，"
        "之前打过一次电话说是处理了，但这两天又开始了。请相关部门管一管。"
    )
    print(f"本地模型：{MODEL} @ {BASE}（enable_thinking=false）")
    case_id = f"local-smoke-{int(time.time())}"
    repository.create_case(case_id, case_id, text, "电话", "processing")
    t0 = time.time()
    try:
        values = run_chain(case_id, text, "电话")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 链路异常：{exc}")
        return 1
    dt = time.time() - t0

    ok = True
    checks = [
        ("理解", (values.get("understanding") or {}).get("summary")),
        ("工单", (values.get("work_order") or {}).get("title")),
        ("分类", (values.get("classification") or {}).get("category_name")),
        ("转派", (values.get("routing") or {}).get("primary")),
        ("答复", (values.get("reply_draft") or {}).get("reply_text")),
    ]
    for name, val in checks:
        mark = "PASS" if val else "FAIL"
        ok = ok and bool(val)
        show = (str(val)[:56] + "…") if val and len(str(val)) > 56 else (val or "（空）")
        print(f"  [{mark}] {name}: {show}")
    print(f"状态：{values.get('status')} · 耗时 {dt:.0f}s · {'全部节点产出' if ok else '存在空节点'}")
    refs = (values.get("reply_draft") or {}).get("policy_refs") or []
    if refs:
        print(f"  政策引用：{'; '.join(refs[:3])}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

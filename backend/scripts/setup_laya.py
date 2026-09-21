# -*- coding: utf-8 -*-
"""下载并冒烟测试 laya-multilingual（中文场景所需的检查点）。

- 只下载 multilingual 子目录（约 647MB），不下载另外两个检查点
- 优先 modelscope（国内快），失败回退 HF 镜像
- 测一条真实中文诉求上的三类原语（noul / choice / score）
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "storage" / "models" / "laya-multilingual"


def download() -> str:
    if (TARGET / "model.safetensors").exists():
        print(f"  已存在：{TARGET}")
        return str(TARGET)
    TARGET.mkdir(parents=True, exist_ok=True)
    try:
        from modelscope import snapshot_download

        t0 = time.monotonic()
        path = snapshot_download(
            "convaiinnovations/laya",
            cache_dir=str(TARGET.parent / "_ms_cache"),
            allow_patterns=["multilingual/*", "*.json", "*.md"],
        )
        print(f"  modelscope 下载完成（{time.monotonic() - t0:.0f}s）：{path}")
        return str(Path(path) / "multilingual")
    except Exception as exc:  # noqa: BLE001
        print(f"  modelscope 失败：{exc}；回退 HF 镜像")
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from huggingface_hub import snapshot_download as hf_download

        return hf_download("convaiinnovations/laya", local_dir=str(TARGET),
                           allow_patterns=["multilingual/*", "*.json"])


def main() -> int:
    print("=== 1. 下载检查点 ===")
    path = download()

    print("\n=== 2. 加载模型（CPU）===")
    import laya

    t0 = time.monotonic()
    try:
        agent = laya.load(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  直接传本地路径失败（{exc}），改用仓库+subfolder")
        agent = laya.load("convaiinnovations/laya", subfolder="multilingual")
    print(f"  加载耗时 {time.monotonic() - t0:.1f}s")

    print("\n=== 3. 真实中文诉求推理 ===")
    state = {
        "诉求原文": "我是鸠江区棠梅小区的住户，小区北门外的兄弟烧烤店每天晚上占道摆桌，"
                    "油烟直接飘进家里，一直到凌晨两点多特别吵，跟物业反映过没人管，请尽快处理。",
        "工单标题": "关于棠梅小区北门烧烤店占道经营及油烟噪音扰民的问题",
    }
    questions = {
        "category": {
            "type": "choice",
            "instructions": "这段群众诉求的核心事项属于哪一类？以诉求的核心事项为准。",
            "criteria": {
                "urban_management": "占道经营、市容环境、违章建筑、餐饮油烟",
                "ecology_environment": "工业排污、噪声与大气污染（生产经营源）",
                "market_regulation": "商品质量、无证经营、消费纠纷",
                "other": "以上均不适用或信息不足",
            },
        },
        "safety_hazard": {
            "type": "noul",
            "instructions": "诉求中是否包含可能危害人身安全的情形？",
        },
        "severity": {
            "type": "score",
            "instructions": "若存在安全隐患，其严重程度处于哪个位置？（无隐患按最低档）",
            "criteria": ["无安全隐患", "影响面较大但无即时人身危险", "有人身安全风险，需立即处置"],
        },
    }
    t0 = time.monotonic()
    res = agent.predict(state, questions)
    dt = (time.monotonic() - t0) * 1000
    print(f"  单次推理耗时 {dt:.0f} ms")
    for k, v in (res.get("answers") or {}).items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

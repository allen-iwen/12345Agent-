# -*- coding: utf-8 -*-
"""图片证据视觉评测：公开许可标注集上的隐患类型与严重程度准确率。

- 数据集：data/eval/vision/real/（16 张 Wikimedia 公开许可照片，逐张登记来源与许可证）
- 评测口径：**不向模型透露任何期望答案**，只给中性的"市民上传的现场照片"上下文
- 指标：隐患类型准确率、严重程度准确率、隐患有无一致率、平均延迟；并列出错例供人工复核
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import vision  # noqa: E402

DATA = Path("data/eval/vision/real")
NEUTRAL_CONTEXT = "市民通过热线上传的现场照片，用于判断事项类别与紧急程度。"


def main() -> int:
    if not vision.available():
        print("视觉模型未配置（VISION_PROVIDER / VISION_API_KEY），无法评测。")
        return 2

    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))["images"]
    print(f"=== 视觉评测：{len(labels)} 张公开许可照片 ===")
    print(f"{'文件':<28}{'期望类型':<12}{'预测类型':<12}{'期望':<6}{'预测':<6}{'延迟':>8}")
    print("-" * 78)

    type_ok = sev_ok = hazard_ok = 0
    done = 0
    latencies: list[float] = []
    mismatches: list[dict] = []

    for item in labels:
        path = DATA / item["file"]
        t0 = time.monotonic()
        try:
            r = vision.analyze(path, NEUTRAL_CONTEXT)
        except Exception as exc:  # noqa: BLE001
            r = {"available": False, "note": str(exc)}
        dt = time.monotonic() - t0
        if not r.get("available"):
            print(f"{item['file']:<28}调用失败：{r.get('note')}")
            mismatches.append({"file": item["file"], "error": r.get("note")})
            continue

        done += 1
        latencies.append(dt)
        ptype = r.get("hazard_type") or ""
        psev = r.get("severity") or ""
        phaz = bool(r.get("hazard"))
        etype, esev, ehaz = item["expected_hazard_type"], item["expected_severity"], item["expected_hazard"]

        t_ok = ptype == etype
        s_ok = psev == esev
        h_ok = phaz == ehaz
        type_ok += t_ok
        sev_ok += s_ok
        hazard_ok += h_ok
        print(f"{item['file']:<28}{etype:<12}{ptype:<12}{esev:<6}{psev:<6}{dt * 1000:>6.0f}ms "
              f"{'√' if t_ok else '×'}{'√' if s_ok else '×'}")
        if not (t_ok and s_ok):
            mismatches.append({
                "file": item["file"], "expected_type": etype, "predicted_type": ptype,
                "expected_severity": esev, "predicted_severity": psev,
                "confidence": r.get("confidence"), "summary": (r.get("summary") or "")[:80],
                "note": item.get("note", ""),
            })

    if done == 0:
        print("\n全部调用失败。")
        return 1

    avg_ms = sum(latencies) / done * 1000
    print("-" * 78)
    print(f"样本 {done} 张｜平均延迟 {avg_ms:.0f}ms")
    print(f"隐患类型准确率：{type_ok}/{done} = {type_ok / done:.1%}")
    print(f"严重程度准确率：{sev_ok}/{done} = {sev_ok / done:.1%}")
    print(f"隐患有无一致率：{hazard_ok}/{done} = {hazard_ok / done:.1%}")

    if mismatches:
        print(f"\n错例 {len(mismatches)} 例（供人工复核，不隐去）：")
        for m in mismatches:
            if "error" in m:
                print(f"  - {m['file']}：调用失败")
            else:
                print(f"  - {m['file']}：期望 {m['expected_type']}/{m['expected_severity']}"
                      f" → 预测 {m['predicted_type']}/{m['predicted_severity']}（{m.get('summary', '')}）")

    out = Path("data/eval/vision/result.json")
    out.write_text(json.dumps({
        "samples": done,
        "model": "MiniMax-M3",
        "type_accuracy": round(type_ok / done, 4),
        "severity_accuracy": round(sev_ok / done, 4),
        "hazard_agreement": round(hazard_ok / done, 4),
        "avg_latency_ms": round(avg_ms, 1),
        "mismatches": mismatches,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

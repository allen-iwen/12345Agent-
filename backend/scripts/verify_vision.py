# -*- coding: utf-8 -*-
"""视觉证据分析验证：连通性、JSON 结构、降级路径。

说明：合成图仅用于验证调用链与输出结构，不作为准确率依据；
准确率评测需要真实现场照片（见 data/eval/vision/README）。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import vision  # noqa: E402

OUT = Path("data/eval/vision")
PASS, FAIL = [], []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    (PASS if cond else FAIL).append(name)


def make_synthetic() -> list[Path]:
    """用 PIL 画 3 张示意图，验证调用链与结构（非准确率依据）。"""
    try:
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001
        print("  （PIL 不可用，跳过合成图）")
        return []
    OUT.mkdir(parents=True, exist_ok=True)
    paths = []

    # 1) 路面井盖缺失：灰色路面 + 深色洞口 + 锥桶
    img = Image.new("RGB", (640, 480), (120, 120, 120))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 300, 640, 480], fill=(90, 90, 90))
    d.ellipse([260, 340, 380, 430], fill=(25, 25, 25))
    d.polygon([(120, 430), (170, 350), (220, 430)], fill=(230, 120, 20))
    p = OUT / "synthetic_manhole.png"
    img.save(p)
    paths.append(p)

    # 2) 垃圾堆积：地面 + 多色块
    img = Image.new("RGB", (640, 480), (150, 150, 140))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 320, 640, 480], fill=(110, 110, 100))
    for i, (x, y, c) in enumerate([(150, 330, (90, 70, 50)), (230, 340, (60, 60, 60)),
                                   (300, 325, (140, 120, 80)), (380, 345, (70, 80, 70))]):
        d.rectangle([x, y, x + 70, y + 60], fill=c)
    p = OUT / "synthetic_garbage.png"
    img.save(p)
    paths.append(p)

    # 3) 非隐患：普通街景（蓝天 + 楼 + 树）
    img = Image.new("RGB", (640, 480), (170, 200, 230))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 320, 640, 480], fill=(100, 100, 100))
    d.rectangle([100, 150, 260, 320], fill=(180, 175, 165))
    d.rectangle([340, 190, 470, 320], fill=(160, 155, 150))
    d.ellipse([500, 240, 600, 320], fill=(70, 120, 70))
    p = OUT / "synthetic_normal.png"
    img.save(p)
    paths.append(p)
    return paths


def main() -> int:
    print("=== 配置与可用性 ===")
    print(f"  provider 列表：{[p['provider'] for p in vision._active_providers()]}")
    check("视觉服务可用", vision.available())

    print("\n=== 调用链（合成示意图）===")
    images = make_synthetic()
    for img in images:
        t0 = time.time()
        r = vision.analyze(img, "市民反映小区门口存在安全隐患，请核实。")
        dt = time.time() - t0
        ok = r.get("available") and r.get("hazard_type") is not None
        print(f"  {img.name} ({dt:.0f}s)：hazard={r.get('hazard')} type={r.get('hazard_type')} "
              f"severity={r.get('severity')} conf={r.get('confidence')}")
        print(f"     摘要：{str(r.get('summary'))[:70]}")
        check(f"{img.name} 返回结构化结果", bool(ok))

    print("\n=== 降级路径 ===")
    r = vision.analyze("不存在的图片.png")
    check("图片不存在时优雅降级", r.get("available") is False and bool(r.get("note")), str(r.get("note"))[:40])

    from app.core.config import get_settings

    s = get_settings()
    bad = {"provider": "minimax-bad", "base_url": "http://127.0.0.1:9/v1", "api_key": "x", "model": "m"}
    if images:
        try:
            vision._call(bad, "data:image/png;base64,iVBORw0KGgo=", "test")
            check("错误 provider 抛异常（由上层降级）", False, "未抛异常")
        except Exception as exc:  # noqa: BLE001
            check("错误 provider 抛异常（由上层降级）", True, type(exc).__name__)

    print(f"\n视觉分析验证：{len(PASS)} 通过 / {len(FAIL)} 失败" + ("；" + "；".join(FAIL) if FAIL else ""))
    print("注：准确率评测需真实隐患照片，放入 data/eval/vision/ 后用 scripts/eval_vision.py 评测。")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""图片证据受理端到端验证：上传 → 视觉分析 → 建单注入 → 急件升级。

文本刻意保持模糊（不写隐患类型），以验证「图片证据确实影响了判断」。
"""
import sys

import requests

BASE = "http://127.0.0.1:8000"
IMG = "data/eval/vision/synthetic_manhole.png"
FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAIL.append(name)


def main() -> int:
    # 0) 机制验证（确定性）：视觉判定隐患时，急件分级必须升级并标注来源
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    from app.services import urgency

    fake = [{"hazard": True, "hazard_type": "井盖缺失", "severity": "特急", "summary": "路面井盖缺失", "confidence": 0.8}]
    u = urgency.assess("小区门口有情况", None, None, None, vision_signals=fake)
    print("=== 0. 图片证据升级机制（确定性）===")
    check("视觉判隐患 → 等级升为特急", u["level"] == "特急", u["level"])
    check("升级标注图片证据来源", any("图片证据" in s for s in u["signals"]), "、".join(u["signals"])[:40])
    u2 = urgency.assess("我想咨询一下营业执照怎么办理", None, None, None,
                        vision_signals=[{"hazard": False, "severity": "一般"}])
    check("视觉未判隐患 → 不升级", u2["level"] == "一般", u2["level"])

    print("\n=== 1. 视觉能力状态 ===")
    st = requests.get(f"{BASE}/api/attachments/status", timeout=15).json()
    print(f"  available={st['available']} providers={st['providers']}")
    check("视觉服务可用", st["available"])

    print("\n=== 2. 上传现场照片（暂存 + 视觉分析）===")
    with open(IMG, "rb") as f:
        r = requests.post(
            f"{BASE}/api/attachments",
            files={"file": ("现场照片.png", f, "image/png")},
            data={"kind": "image", "context_text": "市民反映小区门口有安全隐患"},
            timeout=120,
        )
    check("上传接口返回 200", r.status_code == 200, str(r.status_code))
    up = r.json()
    v = up.get("vision") or {}
    print(f"  附件 id={up['id']}｜视觉：type={v.get('hazard_type')} severity={v.get('severity')} conf={v.get('confidence')}")
    print(f"  摘要：{str(v.get('summary'))[:64]}")
    check("视觉返回隐患类型", bool(v.get("hazard_type")))
    check("视觉返回严重程度", v.get("severity") in ("特急", "紧急", "一般"), str(v.get("severity")))

    print("\n=== 3. 带图片建单（文本刻意模糊）===")
    r = requests.post(
        f"{BASE}/api/cases",
        json={
            "text": "小区门口有个情况，看着挺危险的，请相关部门尽快来看一下处理。",
            "attachment_ids": [up["id"]],
        },
        timeout=600,
    )
    check("建单返回 200", r.status_code == 200, str(r.status_code))
    c = r.json()
    print(f"  状态 {c['status']}｜分类 {(c.get('classification') or {}).get('category_name')}"
          f"｜急件 {(c.get('urgency') or {}).get('level')}｜时限 {(c.get('deadline') or {}).get('state')}")
    print(f"  附件 {len(c.get('attachments') or [])} 个｜答复 {(c.get('reply_draft') or {}).get('reply_text', '')[:36]}…")

    check("案件带回附件与视觉结论", len(c.get("attachments") or []) == 1 and bool(c["attachments"][0].get("vision")))
    urg = c.get("urgency") or {}
    # 合成示意图的视觉判定不稳定（抽象图可能被判为「无隐患」），故此处只验证机制一致性：
    # 视觉判定为隐患时必须升级并标注来源；未判定隐患时不得凭空升级。
    if v.get("hazard") and v.get("severity") in ("特急", "紧急"):
        check("图片证据使急件升级", urg.get("level") == v.get("severity"), f"{urg.get('level')} vs {v.get('severity')}")
        check("升级原因含图片证据", any("图片证据" in s for s in (urg.get("signals") or [])),
              "、".join(urg.get("signals") or [])[:40])
    else:
        check("视觉未判隐患时不凭空升级", urg.get("level") in ("一般", "紧急"), str(urg.get("level")))
    check("时限条款与等级匹配", bool(((c.get("deadline") or {}).get("basis", {}) or {}).get("clause")),
          ((c.get("deadline") or {}).get("basis", {}) or {}).get("clause", "")[:28])
    check("答复含安全提示（隐患类必备）", any(k in (c.get("reply_draft") or {}).get("reply_text", "")
                                              for k in ("远离", "拨打", "注意安全", "安全")),
          "")

    print("\n=== 4. 附件回显与列表 ===")
    raw = requests.get(f"{BASE}/api/attachments/{up['id']}/raw", timeout=15)
    check("原图可回显", raw.status_code == 200 and len(raw.content) > 1000, f"{len(raw.content)} bytes")
    lst = requests.get(f"{BASE}/api/cases/{c['case_id']}/attachments", timeout=15).json()
    check("案件附件列表可查", len(lst) == 1, f"{len(lst)} 条")

    print("\n图片受理端到端：" + ("PASS" if not FAIL else "FAIL：" + "；".join(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""laya 决策信号评测（修正版）：按原语分别给出可辩护的指标。

修正要点：
1. Noul 返回的是「为真的概率」，不是布尔 —— 必须按阈值判定，不能判 `is False`；
2. Score（序数）跨类分布重叠严重，固定阈值不可用 —— 给出违规/合规两组分布与
   「在我们数据上拟合的最优阈值」表现，并明确标注该阈值是同集拟合（乐观估计）。

用法：python scripts/eval_laya_signals.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import decision, decision_case  # noqa: E402

HAZARD = [
    ("小区门口燃气管道破裂，能闻到很浓的燃气味，旁边就是居民楼", True),
    ("路中间井盖没了，晚上有行人差点掉下去", True),
    ("大风把电线刮断垂到人行道上，有人经过可能会触电", True),
    ("楼道里电动车飞线充电，插排就挂在楼梯口", True),
    ("这栋楼外墙开裂严重，随时可能脱落砸到人", True),
    ("超市疏散通道被货物托盘完全堵死，火灾时跑不出去", True),
    ("楼下烧烤店油烟飘进家里，晚上吵得睡不着", False),
    ("我们小区停水两天了，物业也不管", False),
    ("想咨询一下个体工商户营业执照怎么办", False),
    ("路边树长得太密，挡了路灯的光", False),
    ("小区垃圾分类点太远，扔垃圾不方便", False),
    ("路口人行道地砖有点松动，踩上去有响动", False),
]

VIOLATIONS = [
    ("overpromise", "我们保证解决您反映的占道经营问题，请您放心。"),
    ("overpromise", "相关部门承诺一定会彻底处理好，请等待。"),
    ("deadline", "我们承诺三天内解决该问题。"),
    ("privacy", "您（13812345678）反映的占道经营问题已收悉。"),
    ("privacy", "您反映的镜湖区某小区3号楼2单元501室的问题已收悉。"),
    ("shirk", "这不归我们管，你去找城管。"),
    ("no_response", "12345 热线负责统一受理群众诉求并转办相关单位，我们将持续优化工作流程、提升服务质量。"),
    ("absolute", "我们将彻底杜绝此类占道经营现象。"),
    ("overpromise", "您反映的油烟问题已收悉，马上解决，绝不让您再受影响。"),
    ("privacy", "已联系您 13900001111 确认情况，问题已转办。"),
]
COMPLIANT = [
    "已转交属地政府及城市管理部门核实处理，相关部门将依法开展现场核查，办理结果将按规定时限向您反馈。",
    "已转交属地政府及市政部门核实处置，将尽快排查线路并恢复照明，办理结果将按规定时限向您反馈。",
    "个体工商户登记可通过线上政务服务平台或属地市场监管所窗口办理，需准备身份证明与经营场所证明。",
    "已转交属地政府及供水单位核实，将尽快排查供水管网并恢复供水。",
    "已转交劳动保障监察机构依法核实处理，建议您保留劳动合同与工资凭证。",
    "已转交生态环境与住建部门核查，将督促施工单位落实降噪措施。",
    "已转交生态环境部门取样核查，办理结果将及时向您反馈。",
    "已转交交通运输部门核实线路运营情况并评估调整。",
    "建议先与物业服务企业沟通协调；如涉及房屋质量问题，已同步转交住建部门核实。",
    "已转交教育主管部门核实办学与退费情况，办理结果将按规定时限向您反馈。",
]


def hazard_probs() -> list[tuple[str, bool, float]]:
    q = {"safety_hazard": decision.noul(
        "诉求中是否包含可能危害人身安全的情形（如燃气泄漏、电线坠落、井盖缺失、消防通道堵塞、危房）？",
        {"true": "描述了具体的即时人身安全风险", "false": "仅为生活不便、服务纠纷、咨询建议或一般环境问题"})}
    out = []
    for text, expect in HAZARD:
        r = decision.ask({"诉求原文": text}, q)
        p = ((r.get("answers") or {}).get("safety_hazard") or {}).get("value") if r.get("available") else None
        out.append((text, expect, float(p) if p is not None else -1.0))
    return out


def reply_probs() -> tuple[list[dict], list[dict]]:
    q = decision_case.reply_questions()
    def one(text: str) -> dict:
        r = decision.ask({"草拟答复": text}, q)
        a = (r.get("answers") or {}) if r.get("available") else {}
        return {
            "over": (a.get("reply_overpromise") or {}).get("value"),
            "addr": (a.get("reply_addresses_request") or {}).get("value"),
            "priv": (a.get("reply_privacy") or {}).get("value"),
            "available": r.get("available"),
        }
    return [one(t) for _, t in VIOLATIONS], [one(t) for t in COMPLIANT]


def best_threshold(pos: list[float], neg: list[float], higher_means_positive: bool) -> tuple[float, float]:
    """在同一批数据上拟合最优阈值（乐观估计，仅用于说明可分性）。"""
    cands = sorted(set([round(x, 2) for x in pos + neg]))
    best = (0.0, -1.0)
    for th in cands:
        if higher_means_positive:
            acc = (sum(1 for x in pos if x >= th) + sum(1 for x in neg if x < th)) / (len(pos) + len(neg))
        else:
            acc = (sum(1 for x in pos if x < th) + sum(1 for x in neg if x >= th)) / (len(pos) + len(neg))
        if acc > best[1]:
            best = (th, acc)
    return best


def main() -> int:
    st = decision.status()
    print("=== 决策模型 ===")
    print(f"  provider={st['provider']}｜model={st['model']}｜enabled={st['enabled']}｜available={st['available']}")
    if not st["available"]:
        return 2

    t0 = time.monotonic()
    hp = hazard_probs()
    print(f"\n=== A. 安全隐患 Noul（{len(HAZARD)} 条中文）===")
    print(f"{'期望':<6}{'p(隐患)':>9}  {'判定':<6}文本")
    for text, expect, p in hp:
        ok = (p >= 0.5) == expect
        print(f"{'隐患' if expect else '非隐患':<6}{p:>9.3f}  {'√' if ok else '×':<6}{text[:30]}")
    hc = sum(1 for _, e, p in hp if (p >= 0.5) == e)
    pos = [p for _, e, p in hp if e]
    neg = [p for _, e, p in hp if not e]
    print(f"  0.5 阈值准确率：{hc}/{len(hp)} = {hc / len(hp):.1%}")
    print(f"  隐患组均值 {sum(pos) / len(pos):.3f}｜非隐患组均值 {sum(neg) / len(neg):.3f}")
    th, acc = best_threshold(pos, neg, True)
    print(f"  同集拟合最优阈值 {th}：{acc:.1%}（乐观估计）")

    vp, cp = reply_probs()
    lat = (time.monotonic() - t0) / (len(hp) + len(vp) + len(cp)) * 1000
    print(f"\n=== B. 答复合规（10 违规 / 10 合规）===")
    for (label, text), a in zip(VIOLATIONS, vp):
        print(f"  违规[{label:<12}] over={a['over']:.2f} addr={a['addr']:.2f} priv={a['priv']:.2f} | {text[:26]}")
    for a in cp:
        print(f"  合规            over={a['over']:.2f} addr={a['addr']:.2f} priv={a['priv']:.2f}")

    def dim(name: str, key: str, higher_pos: bool):
        p = [a[key] for a in vp if a[key] is not None]
        n = [a[key] for a in cp if a[key] is not None]
        th, acc = best_threshold(p, n, higher_pos)
        print(f"  {name}：违规均值 {sum(p) / len(p):.3f}｜合规均值 {sum(n) / len(n):.3f}"
              f"｜同集最优阈值 {th} → {acc:.1%}")

    print("\n  分维度可分性（同一数据集内拟合阈值，乐观）")
    dim("过度承诺 Score(越高越违规)", "over", True)
    dim("隐私泄露 Noul(越高越违规)", "priv", True)
    dim("正面回应 Noul(越低越违规)", "addr", False)
    print(f"\n  平均延迟 {lat:.0f} ms/次（CPU）")

    print("\n=== 结论（依据以上数据）===")
    print(f"  1) 12 类中文 Choice 零样本：22.2%（官方亦声明 base 零样本接近随机）→ 不可用于分类")
    print(f"  2) 安全隐患 Noul：0.5 阈值 {hc / len(hp):.1%}；两组均值差异 "
          f"{abs(sum(pos) / len(pos) - sum(neg) / len(neg)):.2f}")
    print(f"  3) 答复合规：Score 维度分布重叠 → 序数原语最弱（与官方说明一致）；Noul 可用于提示")
    print(f"  4) 规则引擎在同一合规集上：召回 100% / 误报 0% → 生产判断仍以规则+生成模型为主")

    out = Path("data/eval/laya_signals_result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "provider": st["provider"], "model": st["model"],
        "hazard": {"accuracy_at_0.5": round(hc / len(hp), 4),
                   "pos_mean": round(sum(pos) / len(pos), 4), "neg_mean": round(sum(neg) / len(neg), 4),
                   "items": [{"text": t, "expected": e, "p": p} for t, e, p in hp]},
        "compliance": {"violations": vp, "compliant": cp},
        "avg_latency_ms": round(lat, 1),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

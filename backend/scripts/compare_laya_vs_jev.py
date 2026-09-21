# -*- coding: utf-8 -*-
"""对比同一评测集上 laya（本地开源）与 JEV（OpenRouter alpha）的表现。"""
import json
from pathlib import Path

EV = Path("data/eval")

laya_cls = json.loads((EV / "laya_classify_result.json").read_text(encoding="utf-8"))
jev_cls = json.loads((EV / "openrouter_classify_result.json").read_text(encoding="utf-8"))
laya_sig = json.loads((EV / "laya_signals_result.json").read_text(encoding="utf-8"))
jev_sig = json.loads((EV / "openrouter_signals_result.json").read_text(encoding="utf-8"))


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


print("=" * 78)
print("一、事项分类（12 类中文 Choice，18 条官方样例，留一验证）")
print("=" * 78)
print(f"{'指标':<22}{'laya（本地）':>20}{'JEV（OpenRouter）':>24}")
print("-" * 78)
print(f"{'准确率':<22}{laya_cls['accuracy']:>19.1%}{jev_cls['accuracy']:>23.1%}")
_ls, _js = laya_cls.get("samples", 18), jev_cls.get("samples", 18)
print(f"{'答对 / 总数':<22}{round(laya_cls['accuracy'] * _ls):>14}/{_ls}{round(jev_cls['accuracy'] * _js):>18}/{_js}")
print(f"{'平均延迟':<22}{laya_cls['avg_latency_ms']:>17.0f}ms{jev_cls['avg_latency_ms']:>21.0f}ms")
print(f"{'输入 token':<22}{laya_cls['input_tokens']:>20}{jev_cls['input_tokens']:>24}")
print(f"{'总成本（18 条）':<22}{'$' + format(laya_cls['cost_usd'], '.6f'):>20}{'$' + format(jev_cls['cost_usd'], '.6f'):>24}")
print(f"{'单案成本':<22}{'$0（自托管）':>20}{'$' + format(jev_cls['cost_usd'] / 18, '.6f'):>24}")
g1, g2 = laya_cls["gate_distribution"], jev_cls["gate_distribution"]
print(f"{'门控 auto':<22}{g1['auto']:>20}{g2['auto']:>24}")
print(f"{'门控 confirm':<22}{g1['confirm']:>20}{g2['confirm']:>24}")
print(f"{'门控 human':<22}{g1['human']:>20}{g2['human']:>24}")
print(f"\n  模型版本：laya = convaiinnovations/laya-multilingual（本地）")
print(f"            JEV  = {jev_cls['model']}")

print()
print("=" * 78)
print("二、安全隐患 Noul（12 条中文，0.5 阈值）")
print("=" * 78)
lh, jh = laya_sig["hazard"], jev_sig["hazard"]
print(f"{'指标':<26}{'laya':>16}{'JEV':>18}")
print("-" * 78)
print(f"{'0.5 阈值准确率':<26}{lh['accuracy_at_0.5']:>15.1%}{jh['accuracy_at_0.5']:>17.1%}")
print(f"{'答对 / 总数':<26}{round(lh['accuracy_at_0.5'] * 12):>13}/12{round(jh['accuracy_at_0.5'] * 12):>15}/12")
print(f"{'隐患组均值':<26}{lh['pos_mean']:>16.3f}{jh['pos_mean']:>18.3f}")
print(f"{'非隐患组均值':<26}{lh['neg_mean']:>16.3f}{jh['neg_mean']:>18.3f}")
print(f"{'两组间隔':<26}{abs(lh['pos_mean'] - lh['neg_mean']):>16.3f}{abs(jh['pos_mean'] - jh['neg_mean']):>18.3f}")

print("\n  逐条对照（越接近 1 判为隐患，越接近 0 判为非隐患）：")
print(f"  {'期望':<7}{'laya':>8}{'判定':>6}   {'JEV':>8}{'判定':>6}   文本")
for a, b in zip(lh["items"], jh["items"]):
    ok_l = "√" if (a["p"] >= 0.5) == a["expected"] else "×"
    ok_j = "√" if (b["p"] >= 0.5) == b["expected"] else "×"
    print(f"  {'隐患' if a['expected'] else '非隐患':<7}{a['p']:>8.3f}{ok_l:>5}   {b['p']:>8.3f}{ok_j:>6}   {a['text'][:26]}")

print()
print("=" * 78)
print("三、答复合规三维（10 违规 / 10 合规，同集拟合阈值）")
print("=" * 78)
print(f"{'维度':<30}{'laya 违规/合规均值':>22}{'间隔':>8}   {'JEV 违规/合规均值':>20}{'间隔':>8}")
print("-" * 78)


def report(name, key):
    lp = [v[key] for v in laya_sig["compliance"]["violations"] if v.get(key) is not None]
    ln = [v[key] for v in laya_sig["compliance"]["compliant"] if v.get(key) is not None]
    jp = [v[key] for v in jev_sig["compliance"]["violations"] if v.get(key) is not None]
    jn = [v[key] for v in jev_sig["compliance"]["compliant"] if v.get(key) is not None]
    lgap, jgap = mean(lp) - mean(ln), mean(jp) - mean(jn)
    print(f"{name:<30}{f'{mean(lp):.3f} / {mean(ln):.3f}':>22}{lgap:>8.3f}   "
          f"{f'{mean(jp):.3f} / {mean(jn):.3f}':>20}{jgap:>8.3f}")
    return lgap, jgap


report("过度承诺 score（高=违规）", "over")
report("隐私泄露 noul（高=违规）", "priv")
report("正面回应 noul（低=违规）", "addr")

print("\n  JEV 分维度同集最优阈值表现（取自本次运行）：")
for d in jev_sig.get("compliance_dims", []):
    if d.get("gap", -1) >= 0:
        print(f"    {d['name']:<30}间隔 {d['gap']:.3f}  阈值 {d.get('threshold')} → {d['acc']:.1%}")

print(f"\n  平均延迟：laya {laya_sig['avg_latency_ms']:.0f} ms/次（CPU 本地）"
      f"｜JEV {jev_sig['avg_latency_ms']:.0f} ms/次（云 API）")

# -*- coding: utf-8 -*-
"""Jev 决策信号接入验证：机制（确定性注入）+ 回退（未配置时零影响）。

由于 TypeSafe API Key 尚未就位，本脚本用**注入式**验证机制正确性：
把与真实响应同构的 decision_signals 直接传给三个服务，断言行为符合设计；
再断言未配置（available=False 或无 signals）时行为与接入前完全一致。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.models import Classification, WorkOrder  # noqa: E402
from app.services import decision, dispatch, reply_audit, urgency  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAIL.append(name)


def sig(**conclusions) -> dict:
    """构造与 decision.ask 同构的信号（available=True + conclusions）。"""
    base = {"is_hazard": False, "hazard_level": "一般", "severity_score": 0.0, "mass_impact": False,
            "cross_duty": False, "return_risk_score": 0.0, "repeat_request": False,
            "reply_overpromise_score": 0.0, "reply_addresses_request": True, "reply_privacy": False}
    base.update(conclusions)
    return {"available": True, "provider": "mock", "model": "jev-mock", "conclusions": base}


def main() -> int:
    print("=== 服务级 · 决策模型状态 ===")
    st = decision.status()
    print(f"  available={st['available']} enabled={st['enabled']} provider={st['provider']}")
    print(f"  阈值：高≥{st['thresholds']['high']}（自动采用）/ 低<{st['thresholds']['low']}（转人工）")

    print("\n=== 1. 急件分级：决策模型判定人身安全隐患 → 升级 ===")
    base = urgency.assess("小区门口有个情况，请来看一下", None, None, None)
    check("无信号时为一般", base["level"] == "一般", base["level"])
    u = urgency.assess("小区门口有个情况，请来看一下", None, None, None,
                       decision_signals=sig(is_hazard=True, hazard_level="特急", severity_score=2.0))
    check("判隐患 → 升为特急", u["level"] == "特急", u["level"])
    check("标注决策模型来源", any("决策模型" in s for s in u["signals"]), "、".join(u["signals"])[:44])
    u2 = urgency.assess("小区门口有个情况，请来看一下", None, None, None,
                        decision_signals=sig(mass_impact=True))
    check("大面积影响 → 升为紧急", u2["level"] == "紧急", u2["level"])
    u3 = urgency.assess("小区门口有个情况，请来看一下", None, None, None, decision_signals=sig())
    check("模型未判隐患 → 不升级", u3["level"] == "一般", u3["level"])
    u4 = urgency.assess("咨询营业执照怎么办理", None, None, None, decision_signals={"available": False})
    check("模型不可用 → 行为不变", u4["level"] == "一般", u4["level"])

    print("\n=== 2. 派单：决策模型判定职责交叉 → 退回风险升级 + 依据链留痕 ===")
    wo = WorkOrder(title="关于某小区门口烧烤店占道经营的问题", location="鸠江区某小区",
                   event_description="占道经营油烟扰民", handling_request="依法整治")
    cls = Classification(category_code="urban_management", category_name="城市管理")
    d0 = dispatch.decide(wo, cls, "鸠江区某小区门口烧烤店占道经营")
    d1 = dispatch.decide(wo, cls, "鸠江区某小区门口烧烤店占道经营",
                         decision_signals=sig(cross_duty=True, return_risk_score=2.0))
    check("未注入时按规则判定", "模型判断" not in "".join(e["type"] for e in d0["evidence_chain"]))
    check("注入职责交叉 → 依据链含模型判断",
          any(e["type"] == "模型判断" for e in d1["evidence_chain"]),
          "；".join(e["type"] for e in d1["evidence_chain"]))
    check("职责交叉 → 退回风险为高风险口径",
          "职责交叉" in d1["return_risk"], d1["return_risk"][:34])
    check("派单主承办单位仍由规则决定（模型不越权改派）",
          d0["primary"] == d1["primary"] == "鸠江区政府", d1["primary"])
    check("记录模型风险分", d1.get("model_return_risk_score") == 2.0, str(d1.get("model_return_risk_score")))

    print("\n=== 3. 答复合规：决策模型三维判断 → 追加发现（不改变规则命中） ===")
    reply = ("尊敬的市民：您好！您反映的烧烤店占道经营问题已收悉。现将有关情况答复如下："
             "已转交属地政府核实处理，办理结果将按规定时限向您反馈。感谢您对政府工作的关心与支持！")
    ctx = {"raw_text": "烧烤店占道经营油烟噪音扰民多次反映", "urgency": {"level": "一般"}}
    a0 = reply_audit.audit(reply, [], ctx)
    a1 = reply_audit.audit(reply, [], ctx, decision_signals=sig(reply_overpromise_score=2.0,
                                                                reply_addresses_request=False,
                                                                reply_privacy=True))
    check("规则判定未被降低（原风险仍为低）", a0["risk_level"] in ("无", "低"), a0["risk_level"])
    types1 = {f["type"] for f in a1["findings"]}
    check("模型发现过度承诺", "overpromise" in types1, "、".join(sorted(types1)))
    check("模型发现未正面回应", "no_direct_response" in types1)
    check("模型发现隐私泄露", "privacy_leak" in types1)
    check("模型发现标注来源", any(f.get("source") == "决策模型" for f in a1["findings"]))
    check("风险等级随模型发现升高", a1["risk_level"] == "高", a1["risk_level"])
    a2 = reply_audit.audit(reply, [], ctx, decision_signals=sig())
    check("模型无发现 → 与规则判定一致", a2["risk_level"] == a0["risk_level"], a2["risk_level"])

    print("\n=== 4. 回退：未配置 Key 时三个判断点均不受影响 ===")
    off = {"available": False, "note": "未配置决策模型"}
    check("急件回退", urgency.assess("咨询", None, None, None, decision_signals=off)["level"] == "一般")
    check("派单回退", dispatch.decide(wo, cls, "鸠江区某小区", decision_signals=off)["primary"] == "鸠江区政府")
    check("合规回退", reply_audit.audit(reply, [], ctx, decision_signals=off)["risk_level"] == a0["risk_level"])

    print(f"\nJev 决策信号接入验证：{len(FAIL) == 0 and 'PASS' or 'FAIL：' + '；'.join(FAIL)}")
    if not st["available"]:
        print("注：当前未配置 TypeSafe Key，以上为**注入式机制验证**；")
        print("    Key 就位后只需把 DECISION_ENABLED 置 true，四个判断点（分类/急件/派单/合规）同时生效。")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

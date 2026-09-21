# -*- coding: utf-8 -*-
"""答复合规审查验证：违规召回率与合规误报率（构造集，可复现）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import reply_audit  # noqa: E402

REQUEST = "镜湖区某小区门口烧烤店每天晚上占道经营到凌晨，油烟呛人噪音吵得睡不着，多次反映没人管。"

_OK = (
    "尊敬的市民：您好！您反映的镜湖区某小区门口烧烤店占道经营及油烟噪音扰民问题已收悉。"
    "现将有关情况答复如下：一、受理情况：您反映的烧烤店占道经营问题已转交属地政府及城市管理部门核实处理。"
    "二、办理方向：相关部门将依法对占道经营行为开展现场核查，督促经营者规范经营并落实油烟净化措施。"
    "三、后续安排：办理结果将按规定时限向您反馈。感谢您对政府工作的关心与支持！"
)

CONTEXT_NORMAL = {"raw_text": REQUEST, "event_description": REQUEST, "urgency": {"level": "一般"}}
CONTEXT_URGENT = {
    "raw_text": "镜湖区某小区门口燃气管道破裂，能闻到很浓的燃气味，非常危险。",
    "event_description": "燃气泄漏",
    "urgency": {"level": "特急"},
    "manual_action": "立即通知燃气公司与消防",
}

# 10 条合规答复（同主题、不同表述；不得命中任何规则）
COMPLIANT = [
    _OK,
    _OK.replace("烧烤店", "餐饮店").replace("油烟呛人", "油烟排放"),
    _OK.replace("已转交属地政府及城市管理部门", "已转属地政府会同城市管理部门"),
    _OK.replace("督促经营者规范经营并落实油烟净化措施", "督促经营者依法整改并加强日常巡查"),
    _OK.replace("三、后续安排：办理结果将按规定时限向您反馈。", "三、后续安排：我们将持续跟进办理进度，及时向您反馈。"),
    _OK.replace("二、办理方向：", "二、核查情况："),
    _OK.replace("一、受理情况：", "一、受理与转办："),
    _OK.replace("噪音吵得睡不着", "夜间噪声影响休息"),
    _OK.replace("多次反映没人管", "问题尚未得到解决"),
    _OK.replace("感谢您对政府工作的关心与支持！", "感谢您的理解与支持！"),
]

# 10 条违规答复（各含一类明确违规）
_GAS_OK = (
    "尊敬的市民：您好！您反映的镜湖区某小区门口燃气管道破裂、燃气味浓的问题已收悉。"
    "现将有关情况答复如下：一、受理情况：已转交属地政府及燃气运营单位核实处置。"
    "二、办理方向：相关单位将依法开展现场核查与抢修。三、后续安排：办理结果将按规定时限向您反馈。"
    "感谢您对政府工作的关心与支持！"
)
VIOLATING: list[dict] = [
    {"name": "过度承诺（关键词）", "text": _OK.replace("依法对占道经营行为开展现场核查", "保证解决您反映的占道经营问题"), "ctx": CONTEXT_NORMAL, "refs": []},
    {"name": "过度承诺（句式）", "text": _OK.replace("督促经营者规范经营", "承诺一定会彻底处理好"), "ctx": CONTEXT_NORMAL, "refs": []},
    {"name": "承诺具体时限", "text": _OK.replace("办理结果将按规定时限向您反馈", "我们承诺三天内解决该问题"), "ctx": CONTEXT_NORMAL, "refs": []},
    {"name": "时限承诺（本周内）", "text": _OK.replace("办理结果将按规定时限向您反馈", "本周内拆除完毕"), "ctx": CONTEXT_NORMAL, "refs": []},
    {"name": "绝对化用语", "text": _OK.replace("督促经营者规范经营", "彻底杜绝此类占道经营现象"), "ctx": CONTEXT_NORMAL, "refs": []},
    {"name": "隐私泄露（手机号）", "text": _OK.replace("您反映的", "您（13812345678）反映的"), "ctx": CONTEXT_NORMAL, "refs": []},
    {"name": "推诿表述", "text": _OK.replace("已转交属地政府及城市管理部门核实处理", "这不归我们管，你去找城管"), "ctx": CONTEXT_NORMAL, "refs": []},
    {"name": "未正面回应诉求", "text": "尊敬的市民：您好！您反映的问题已收悉。12345政务服务便民热线负责统一受理群众诉求并转办相关单位，我们将持续优化工作流程、提升服务质量。感谢您对政府工作的关心与支持！", "ctx": CONTEXT_NORMAL, "refs": []},
    {"name": "隐患缺安全提示", "text": _GAS_OK.replace("已转交属地政府及燃气运营单位核实处置", "已转属地政府处置"), "ctx": CONTEXT_URGENT, "refs": []},
    {"name": "政策引用不可溯", "text": _OK, "ctx": CONTEXT_NORMAL, "refs": ["中华人民共和国不存在的法"]},
]


def main() -> int:
    print("=== 违规答复召回（10 条）===")
    detected = 0
    for item in VIOLATING:
        r = reply_audit.audit(item["text"], item["refs"], item["ctx"])
        hit = r["risk_level"] in ("高", "中")
        detected += hit
        labels = "、".join(f["label"] for f in r["findings"][:3]) or "—"
        print(f"  [{'PASS' if hit else 'FAIL'}] {item['name']:16s} → 风险 {r['risk_level']}（{labels}）")

    print("\n=== 合规答复误报（10 条）===")
    fp = 0
    for i, text in enumerate(COMPLIANT, 1):
        r = reply_audit.audit(text, [], CONTEXT_NORMAL)
        flagged = r["risk_level"] in ("高", "中")
        fp += flagged
        labels = "、".join(f["label"] for f in r["findings"][:3]) or "—"
        print(f"  [{'PASS' if not flagged else 'FAIL'}] 合规#{i:<2d} → 风险 {r['risk_level']}（{labels}）")

    recall = detected / len(VIOLATING)
    fpr = fp / len(COMPLIANT)
    print(f"\n违规召回率：{detected}/{len(VIOLATING)} = {recall:.0%}（阈值 ≥90%）")
    print(f"合规误报率：{fp}/{len(COMPLIANT)} = {fpr:.0%}（阈值 ≤10%）")
    ok = recall >= 0.9 and fpr <= 0.1
    print("\n答复合规审查验证：" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""三支柱本地验证：派单命中率、急件分级、治理提示。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.models import Classification, Understanding, WorkOrder  # noqa: E402
from app.services import dispatch, governance, urgency  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAIL.append(name)


def norm(s: str) -> str:
    import re
    s = re.sub(r"[\s（）()]", "", s or "")
    return s.replace("市", "").replace("政府", "").replace("管理", "").replace("开发区", "经开区")


def pillar1() -> None:
    print("\n=== 支柱一：属地+部门双维派单（官方 18 条样例）===")
    catalog = {c["name"]: c["code"] for c in json.loads(
        (Path("data/categories/category_catalog.json")).read_text(encoding="utf-8"))["categories"]}
    rows = [json.loads(l) for l in Path("data/processed/work_orders.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    hit = contains = 0
    paths: dict[str, int] = {}
    for r in rows:
        actual = r.get("handling_departments") or []
        wo = WorkOrder(title=r["title"], region=r.get("region", "芜湖市"), location=r.get("region", "待确认"),
                       event_description=r["request_content"][:600], handling_request="依法核实处理")
        cls = Classification(category_code=catalog.get(r["category"]), category_name=r["category"])
        d = dispatch.decide(wo, cls, r["request_content"])
        paths[d["path"]] = paths.get(d["path"], 0) + 1
        if actual and norm(d["primary"]) == norm(actual[0]):
            hit += 1
        if any(norm(d["primary"]) == norm(x) for x in actual):
            contains += 1
    n = len(rows)
    print(f"  决策路径分布：{paths}")
    check(f"主办命中率 ≥ 90%（{hit}/{n} = {hit / n:.1%}）", hit / n >= 0.90)
    check(f"命中历史承办集合 ≥ 90%（{contains}/{n} = {contains / n:.1%}）", contains / n >= 0.90)
    # 依据链完整性
    d0 = dispatch.decide(WorkOrder(title="关于某小区门口积水的问题", location="镜湖区", event_description="暴雨后积水", handling_request="尽快排水"),
                         Classification(category_code="urban_management", category_name="城市管理"), "镜湖区某小区积水")
    check("依据链含政策依据与属地判定", len(d0["evidence_chain"]) >= 2 and any(e["type"] == "政策依据" for e in d0["evidence_chain"]))
    check("属地主办路径正确（镜湖区政府）", d0["primary"] == "镜湖区政府" and d0["path"] == "属地主办", d0["primary"])
    sp = dispatch.decide(WorkOrder(title="公交线路未恢复", event_description="公交线路问题", handling_request="恢复原线"), Classification(category_code="transportation"), "公交线路未恢复原线")
    check("专业直派路径正确（公交）", sp["path"] == "专业直派" and sp["primary"] == "市公安局", f"{sp['path']}/{sp['primary']}")


def pillar2() -> None:
    print("\n=== 支柱二：急件识别与时限分级 ===")
    cases = [
        ("小区燃气管道破裂有燃气味，非常危险", "特急"),
        ("整栋楼停水两天了，居民无法生活", "紧急"),
        ("我想咨询一下营业执照怎么办", "一般"),
        ("井盖丢失，晚上有人差点掉下去", "特急"),
    ]
    for text, expect in cases:
        r = urgency.assess(text, Understanding(summary=text, urgent=False), None, None)
        check(f"「{text[:12]}…」→ {expect}", r["level"] == expect, f"实际={r['level']}｜{r['limit_hint'][:24]}")
    r = urgency.assess("路灯不亮", Understanding(summary="路灯不亮", urgent=True), None, None)
    check("理解节点标记紧急 → 至少紧急级", r["level"] in ("紧急", "特急"), r["level"])
    check("分级含政策依据", bool(r["basis"].get("name")))


def pillar3() -> None:
    print("\n=== 支柱三：诉求治理（重复诉求/退回风险）===")
    from app.schemas.models import Case, Routing

    base = dict(case_id="gov-test-1", raw_text="关于某小区门口烧烤店占道经营的问题，我已经多次反映仍未解决",
                status="awaiting_review", created_at="2026-09-20T10:00:00", updated_at="2026-09-20T10:00:00")
    wo = WorkOrder(title="烧烤店占道经营", location="鸠江区某小区", event_description="占道经营油烟扰民", handling_request="依法整治")
    cls = Classification(category_code="urban_management", category_name="城市管理", confidence=0.8)
    routing = Routing(primary="鸠江区政府", departments=[{"name": "鸠江区政府", "role": "建议承办单位"},
                                                          {"name": "市城市管理局", "role": "业务指导单位"},
                                                          {"name": "市生态环境局", "role": "协办单位"}],
                      return_risk="职责交叉（3 个单位共同承办），历史上易发生退回重派，建议派前协调并抄送属地热线主管部门督促（依据：规范「不得随意退回」条款）")
    case = Case(**base, work_order=wo, classification=cls, routing=routing)
    g = governance.assess(case)
    print(f"  治理包：repeat={bool(g.get('repeat'))} return_risk={bool(g.get('return_risk'))} 建议={g.get('suggestions')}")
    check("识别重复诉求标记", bool(g.get("repeat") and g["repeat"]["is_repeat"]))
    check("识别退回风险并给建议", bool(g.get("return_risk")) and any("抄送" in s for s in g.get("suggestions", [])))
    case2 = Case(**{**base, "case_id": "gov-test-2", "raw_text": "关于路灯不亮的问题"},
                 work_order=WorkOrder(title="路灯不亮", location="镜湖区某路", event_description="路灯多日不亮", handling_request="修复"),
                 classification=cls, routing=Routing(primary="镜湖区政府", return_risk="权责清晰，可直接转具体承办单位"))
    g2 = governance.assess(case2)
    check("清晰权责不误报退回风险", not g2.get("return_risk"))


if __name__ == "__main__":
    pillar1()
    pillar2()
    pillar3()
    print(f"\n三支柱验证：{'全部通过' if not FAIL else '失败项：' + '；'.join(FAIL)}")
    sys.exit(1 if FAIL else 0)

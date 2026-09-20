# -*- coding: utf-8 -*-
"""派单策略验证：通用做法（按类别推市直部门） vs 我们的做法（属地优先）比对官方样例实际承办单位。

数据：18 条官方样例工单的 handling_departments（历史实际办理单位）作为金标准。
说明：这是"与历史实际承办单位的一致性"验证，样本 18 条，用于方法对比而非统计推断。
"""
import json
import re
import sys
from pathlib import Path

# 芜湖属地区划 → 属地政府（含开发区）；按关键词长度降序匹配（长优先，避免"弋江区"抢走"高新区（弋江区）"）
DISTRICTS = [
    ("高新技术产业开发区", "高新区（弋江区）"), ("高新区（弋江区）", "高新区（弋江区）"),
    ("三山经济开发区", "三山经济开发区"), ("经济技术开发区", "经济技术开发区"),
    ("南陵县", "南陵县政府"), ("鸠江区", "鸠江区政府"), ("镜湖区", "镜湖区政府"),
    ("弋江区", "弋江区政府"), ("湾沚区", "湾沚区政府"), ("繁昌区", "繁昌区政府"),
    ("无为市", "无为市政府"), ("三山", "三山经济开发区"), ("经开区", "经济技术开发区"),
    ("高新区", "高新区（弋江区）"),
]
DISTRICTS.sort(key=lambda kv: -len(kv[0]))

# 专业直派：行业性极强的诉求，按业务逻辑直派专业承办单位（对应规范"权责清晰可直接转承办单位"）
SPECIALIST_RULES = [
    (("公交线路", "公交站", "公交公司", "公交车站", "公交车"), ["市公安局", "芜湖公交公司"],
     "城市公共交通运营属专业领域：公安交管负责线路秩序，公交运营单位负责运力调整"),
    (("12315", "消费投诉", "消费维权", "商家拒绝退", "虚假宣传", "假冒伪劣"), ["12315 中心"],
     "消费维权诉求直派 12315 消费者投诉举报中心"),
]

# 通用做法：事项类别 → 市直主管部门（多数队伍会这样直接推部门）
CATEGORY_TO_CITY_DEPT = {
    "城市管理": "市城市管理局", "生态环境": "市生态环境局", "市场监管": "市市场监督管理局",
    "交通运输": "市交通运输局", "城乡建设": "市住房和城乡建设局", "公共安全": "市公安局",
    "公共服务": "市城市管理局", "卫生健康": "市卫生健康委员会",
    "劳动和社会保障": "市人力资源和社会保障局", "科教文体": "市教育局",
    "农林水土": "市农业农村局", "经济财贸": "市地方金融监督管理局",
}


def norm(s: str) -> str:
    """归一化单位名：去'市'、'政府'、'局'等后缀差异，便于比对。"""
    s = re.sub(r"[\s（）()]", "", s or "")
    s = s.replace("市", "").replace("政府", "").replace("管理", "").replace("开发区", "经开区")
    return s


def locate_district(text: str) -> str | None:
    for kw, gov in DISTRICTS:
        if kw in text:
            return gov
    return None


def specialist(text: str) -> tuple[str, str] | None:
    """专业直派：命中行业性规则时返回（承办单位, 依据）。"""
    for kws, depts, reason in SPECIALIST_RULES:
        if any(k in text for k in kws):
            return depts[0], reason
    return None


def dispatch(text: str, category: str) -> tuple[str, str]:
    """三层派单决策：专业直派 → 属地主办 → 类别兜底。返回（主办单位, 决策路径）。"""
    sp = specialist(text)
    if sp:
        return sp[0], "专业直派"
    district = locate_district(text)
    if district:
        return district, "属地主办"
    return CATEGORY_TO_CITY_DEPT.get(category, "未知"), "类别兜底"


def main() -> int:
    rows = [json.loads(l) for l in Path("data/processed/work_orders.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    stat_a_hit = stat_b_hit = stat_b_contains = 0
    by_path: dict[str, int] = {}
    print(f"{'类别':<10} {'实际承办（历史）':<22} {'通用做法预测':<20} {'三层决策预测':<18} 路径 命中")
    print("-" * 108)
    for r in rows:
        actual = r.get("handling_departments", [])
        actual_main = actual[0] if actual else ""
        text = f"{r['title']} {r.get('request_content', '')}"

        pred_a = CATEGORY_TO_CITY_DEPT.get(r["category"], "未知")
        pred_b, path = dispatch(text, r["category"])
        by_path[path] = by_path.get(path, 0) + 1

        hit_a = norm(pred_a) == norm(actual_main) or norm(pred_a) in [norm(x) for x in actual]
        hit_b = norm(pred_b) == norm(actual_main)
        contains_b = norm(pred_b) in [norm(x) for x in actual]
        stat_a_hit += hit_a
        stat_b_hit += hit_b
        stat_b_contains += contains_b

        print(f"{r['category']:<10} {'、'.join(actual):<22} {pred_a:<20} {pred_b:<18} {path:<6} "
              f"A{'√' if hit_a else '×'} B{'√' if hit_b else '×'}")

    n = len(rows)
    print("-" * 108)
    print(f"通用做法（按类别推市直部门）主办命中：{stat_a_hit}/{n} = {stat_a_hit / n:.1%}")
    print(f"三层决策（专业直派/属地主办/类别兜底）主办命中：{stat_b_hit}/{n} = {stat_b_hit / n:.1%}")
    print(f"三层决策（出现在历史承办单位中）：{stat_b_contains}/{n} = {stat_b_contains / n:.1%}")
    print(f"决策路径分布：{by_path}")

    # 历史实际派单结构：属地 vs 市直
    local_gov = sum(1 for r in rows if any(k in (r.get("handling_departments") or [""])[0] for k in ["政府", "开发区", "高新区"]))
    print(f"\n历史实际主办单位结构：属地政府/开发区 {local_gov}/{n} = {local_gov / n:.0%}｜市直部门 {n - local_gov}/{n} = {(n - local_gov) / n:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

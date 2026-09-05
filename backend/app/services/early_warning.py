"""「未诉先办」苗头预警：同点位同类诉求的短期聚集检测。

社会背景：同一路段/小区/商圈的同类问题在短期内被多人反映，往往是个体诉求
升级为群体性矛盾的前兆（如片区停水、线路改道、商户集中扰民）。热线侧若能在
第 2~3 件时就识别聚集并提示"转主动治理"，可把矛盾化解在扩散之前——这正是
国办发〔2020〕53 号推广"接诉即办"经验后，北京等地进一步提出"未诉先办"的
工作方向。

判定规则（规则式，可解释、零 LLM 成本）：
1. 取本案分类（category_code）与工单地点/标题/事件描述文本；
2. 扫描近 window_days 日内的其他案件：同分类 + 地点同源（双方文本存在
   ≥3 字、且含地点线索字「路/街/巷/道/桥/站/苑/府/小区/村/镇」的公共子串）；
3. 命中 ≥ threshold 件 → 生成 early_warning（含同源案件清单与治理建议）。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.repositories import cases as repository

WINDOW_DAYS = 7
THRESHOLD = 2  # 除本案外 ≥2 件同源即触发（合计 ≥3 件）

# 行政区泛词剔除（各区县名/行政层级，判别力低）
_PLACE_STOP = re.compile(
    r"(芜湖市|芜湖|镜湖区|鸠江区|弋江区|经开区|经济技术开发区|三山经开区|南陵县|无为市|湾沚区|繁昌区|安徽省)"
)
# 地点线索字：公共子串须至少含其一，才认定"同点位"
_LCUE = ("路", "街", "巷", "道", "桥", "站", "苑", "府", "村", "镇", "小区", "市场", "广场")


def _norm_text(location: str, title: str, desc: str) -> str:
    """归一化地点文本：去行政区泛词、去标点，只留连续汉字段。"""
    text = " ".join([location or "", title or "", desc or ""])
    text = _PLACE_STOP.sub(" ", text)
    return " ".join(t for t in re.split(r"[^\u4e00-\u9fa5]+", text) if t)


def _shared_place(a: str, b: str) -> str | None:
    """返回双方首个 ≥3 字、含地点线索字的公共子串（无则 None）。"""
    for n in (5, 4, 3):  # 优先长匹配
        for i in range(len(a) - n + 1):
            seg = a[i : i + n]
            if any(c in seg for c in _LCUE) and seg in b:
                return seg
    return None


def detect(case) -> dict | None:
    """对案件做苗头聚集检测；返回 None 或预警结构。case 为 schemas.Case。"""
    wo = case.work_order
    cls = case.classification
    if wo is None or cls is None or not cls.category_code:
        return None

    my_text = _norm_text(wo.location, wo.title, wo.event_description)
    if len(my_text) < 3:
        return None

    since = (datetime.now() - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = repository.list_cases(limit=200)
    hits: list[dict] = []
    shared_segs: set[str] = set()
    for r in rows:
        if r["case_id"] == case.case_id:
            continue
        if (r.get("created_at") or "") < since:
            continue
        r_cls = r.get("classification") or {}
        if r_cls.get("category_code") != cls.category_code:
            continue
        r_wo = r.get("work_order") or {}
        r_text = _norm_text(r_wo.get("location") or "", r_wo.get("title") or "", r_wo.get("event_description") or "")
        seg = _shared_place(my_text, r_text)
        if seg:
            shared_segs.add(seg)
            hits.append(
                {
                    "case_id": r["case_id"],
                    "title": r_wo.get("title") or (r.get("raw_text") or "")[:24],
                    "created_at": (r.get("created_at") or "")[:16],
                    "status": r.get("status"),
                    "shared_place": seg,
                }
            )

    if len(hits) < THRESHOLD:
        return None

    segs = sorted(shared_segs, key=lambda s: (-len(s), s))
    segs = [re.sub(r"^[于在近靠至到往沿]", "", s) or s for s in segs]
    place = segs[0]
    return {
        "kind": "未诉先办 · 苗头预警",
        "message": (
            f"近 {WINDOW_DAYS} 日「{place}」周边同分类（{cls.category_name}）诉求已达 "
            f"{len(hits) + 1} 件（含本案）。同类聚集可能预示共性成因，建议并案核查、"
            f"转主动治理工单，避免矛盾扩散引发群体性投诉。"
        ),
        "related": hits[:5],
        "window_days": WINDOW_DAYS,
        "total": len(hits) + 1,
    }

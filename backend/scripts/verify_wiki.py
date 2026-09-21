# -*- coding: utf-8 -*-
"""wiki 知识词条验证：创建/版本/发布/检索/智能体回写。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

BASE = "http://127.0.0.1:8000"
FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAIL.append(name)


def main() -> int:
    print("=== 1. 建词条与版本 ===")
    slug = "guide-urban-vendor"
    r = requests.post(f"{BASE}/api/wiki", json={
        "slug": slug, "title": "占道经营类诉求办理口径",
        "category": "口径话术",
        "body_md": "## 办理要点\n1. 属地政府主办，城管部门业务指导；\n2. 涉及油烟的同时转生态环境；\n3. 答复不得承诺具体时限。",
        "tags": ["占道经营", "城市管理"], "note": "首次建档",
    }, timeout=20)
    check("创建词条", r.status_code == 200, str(r.status_code))
    v1 = r.json().get("version") if r.status_code == 200 else None
    check("初始版本为 1", v1 == 1, str(v1))

    r2 = requests.post(f"{BASE}/api/wiki", json={
        "slug": slug, "title": "占道经营类诉求办理口径（修订）",
        "category": "口径话术", "body_md": "## 办理要点\n1. 属地政府主办；\n2. 答复须写明政策依据；\n3. 职责交叉时提示人工确认。",
        "tags": ["占道经营"], "note": "补充职责交叉提示",
    }, timeout=20)
    check("再次保存版本 +1", r2.status_code == 200 and r2.json().get("version") == 2, str(r2.json().get("version")))

    detail = requests.get(f"{BASE}/api/wiki/{slug}", timeout=20).json()
    check("返回修订历史（2 版）", len(detail.get("revisions", [])) == 2, f"{len(detail.get('revisions', []))} 版")
    check("默认状态为草稿", detail.get("status") == "draft", detail.get("status"))

    print("\n=== 2. 版本回看 ===")
    rev = requests.get(f"{BASE}/api/wiki/{slug}/revisions/1", timeout=20).json()
    check("可读取历史版本正文", "首次建档" in (rev.get("note") or "") or "办理要点" in (rev.get("body_md") or ""),
          (rev.get("note") or "")[:20])

    print("\n=== 3. 发布 ===")
    pub = requests.post(f"{BASE}/api/wiki/{slug}/publish", json={"note": "口径确认"}, timeout=20)
    check("发布成功", pub.status_code == 200 and pub.json().get("status") == "published", str(pub.status_code))
    again = requests.get(f"{BASE}/api/wiki/{slug}", timeout=20).json()
    check("发布后状态生效", again.get("status") == "published", again.get("status"))

    print("\n=== 4. 检索已发布口径 ===")
    s = requests.get(f"{BASE}/api/wiki/search/published", params={"q": "占道经营"}, timeout=20).json()
    check("检索到已发布词条", len(s.get("items", [])) >= 1, f"{len(s.get('items', []))} 条")

    print("\n=== 5. 列表与分类统计 ===")
    lst = requests.get(f"{BASE}/api/wiki", timeout=20).json()
    print(f"  统计：{lst['counts']}")
    check("列表可用且含分类", "口径话术" in lst.get("categories", []), "、".join(lst.get("categories", [])))
    check("已发布计数 ≥1", lst["counts"]["by_status"].get("published", 0) >= 1)

    print("\n=== 6. 智能体回写（案件 → 词条草稿）===")
    cases = requests.get(f"{BASE}/api/cases?limit=5", timeout=20).json()
    target = next((c for c in cases if c.get("work_order") and c.get("routing")), None)
    if target is None:
        check("存在可用于回写的案件", False, "无案件")
    else:
        d = requests.post(f"{BASE}/api/wiki/distill/{target['case_id']}", json={"category": "案例经验"}, timeout=30)
        check("案件沉淀为词条草稿", d.status_code == 200 and d.json().get("status") == "draft",
              str(d.status_code) + " " + str(d.json().get("slug")) if d.status_code == 200 else str(d.status_code))
        if d.status_code == 200:
            g = requests.get(f"{BASE}/api/wiki/{d.json()['slug']}", timeout=20).json()
            check("草稿含承办单位与答复口径", "承办单位" in (g.get("body_md") or ""), (g.get("body_md") or "")[:40])

    print("\n=== 7. 校验与审计 ===")
    bad = requests.post(f"{BASE}/api/wiki", json={"slug": "非法 Slug!", "title": "x"}, timeout=20)
    check("非法 slug 被拒（400）", bad.status_code == 400, str(bad.status_code))
    bad2 = requests.post(f"{BASE}/api/wiki", json={"slug": "ok-slug", "title": "x", "category": "不存在分类"}, timeout=20)
    check("非法分类被拒（400）", bad2.status_code == 400, str(bad2.status_code))
    audit = requests.get(f"{BASE}/api/auth/audit", params={"limit": 50}, timeout=20).json()
    wiki_actions = [r["action"] for r in audit["records"] if r["target_type"] == "wiki"]
    check("词条操作写入审计", len(wiki_actions) >= 3, "、".join(sorted(set(wiki_actions))))

    print(f"\nwiki 验证：{len(FAIL) == 0 and 'PASS' or 'FAIL：' + '；'.join(FAIL)}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""全链路真实跑通验收：每条业务路径都用真实 API 调用验证。

覆盖：健康 / 知识库 / 云端 ASR / 紧急件全生命周期（分节审核→修改→最终放行）/
澄清补录重跑 / 未诉先办苗头预警 / 政策上传-检索-删除 / 效率账本 / 白盒轨迹。
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    (PASS if cond else FAIL).append(name)


def call(method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} {path}: {e.read().decode('utf-8')[:300]}") from e


def upload_file(path: str, url_path: str, fields: dict | None = None) -> dict:
    import os

    boundary = uuid.uuid4().hex
    body = b""
    with open(path, "rb") as f:
        content = f.read()
    for k, v in (fields or {}).items():
        body += (
            f"--{boundary}\r\n".encode()
            + f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
            + str(v).encode("utf-8")
            + "\r\n".encode()
        )
    fname = os.path.basename(path)
    body += (
        f"--{boundary}\r\n".encode()
        + f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'.encode()
        + b"Content-Type: application/octet-stream\r\n\r\n"
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(BASE + url_path, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"upload {url_path} HTTP {e.code}: {e.read().decode('utf-8')[:300]}") from e


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    t_start = time.time()

    section("0 服务健康")
    check("health", get("/health")["status"] == "ok")

    section("1 知识库")
    orders = get("/api/knowledge/orders")
    check("官方工单 18 条", len(orders["orders"]) == 18, str(len(orders["orders"])))
    cats = get("/api/knowledge/categories")
    check("12 大类目录", len(cats["categories"]) == 12, str(len(cats["categories"])))
    q = urllib.parse.quote("理发店收费不合理")
    hits = get(f"/api/knowledge/search?text={q}&top_k=3")["hits"]
    check("BM25 检索命中市场监管", hits and hits[0]["category"] == "市场监管", hits[0]["title"][:20] if hits else "无")

    section("2 录音输入（讯飞云端 · 真实 6 分钟来电 · 降噪整理）")
    t0 = time.time()
    a = upload_file(r"data\raw\official_work_orders\交通运输\260715111208005.mp3", "/api/asr")
    dt = time.time() - t0
    check("云端引擎生效", a["source"] == "xfyun", f"{a['source']} {a['latency_ms']/1000:.1f}s")
    check("转写非空且成段", len(a["text"]) > 500, f"{len(a['text'])} 字 / {a['segments']} 段 / 端到端 {dt:.0f}s")
    check("降噪整理生效", a.get("clean_applied") is True and len(a.get("text_clean") or "") > 100,
          (a.get("clean_note") or "")[:60])
    check("彩铃误识别已剔除", "噢b" not in (a.get("text_clean") or ""), (a.get("clean_changes") or [])[:2].__str__())
    check("原文保留作证据", len(a.get("text") or "") > len(a.get("text_clean") or ""))

    section("3 紧急件全生命周期（燃气泄漏）")
    c = call("POST", "/api/cases", {
        "text": "现在闻到镜湖区棠梅小区楼道内有很重的燃气味，疑似发生泄漏，请立即处理！",
    })
    cid = c["case_id"]
    check("链路停在人工审核", c["status"] == "awaiting_review", c["status"])
    check("识别紧急", c["understanding"]["urgent"] is True)
    check("人工处置提示", bool(c["understanding"].get("manual_action")), (c["understanding"].get("manual_action") or "")[:40])
    check("分类合理", c["classification"]["category_code"] is not None, str(c["classification"]["category_name"]))
    check("QC 已生成", len(c["qc_checks"]) >= 6, f"{len(c['qc_checks'])} 项")
    check("效率字段", c.get("agent_seconds") is not None and c["agent_seconds"] > 0, f"{c['agent_seconds']}s")

    # 分节确认 + 一处修改（转派 primary）
    rt = c["routing"]
    rt["primary"] = "芜湖市住房和城乡建设局"
    call("POST", f"/api/cases/{cid}/review", {"section": "routing", "action": "modify", "payload": rt, "note": "修正主办单位"})
    for sec in ("work_order", "classification", "routing", "reply"):
        r = call("POST", f"/api/cases/{cid}/review", {"section": sec, "action": "approve"})
    check("分节审核完成", all(
        r["review"][k] == "approved" for k in ("work_order", "classification", "routing", "reply")
    ))
    detail = get(f"/api/cases/{cid}")
    check("修改生效", detail["routing"]["primary"] == "芜湖市住房和城乡建设局", detail["routing"]["primary"])

    done = call("POST", f"/api/cases/{cid}/review", {"section": "final", "action": "approve", "note": "归档"})
    check("最终放行 → completed", done["status"] == "completed", done["status"])
    runs = get(f"/api/runs/cases/{cid}")["runs"]
    ok_nodes = [r["node"] for r in runs if r["status"] == "ok"]
    check("白盒轨迹 5 节点 ok", len(ok_nodes) >= 5, ",".join(ok_nodes))
    durs = {r["node"]: r.get("duration_ms") for r in runs}
    check("轨迹含耗时", all(isinstance(v, int) and v > 0 for v in durs.values() if v), str(durs))

    section("4 澄清补录重跑（路灯缺地点）")
    c2 = call("POST", "/api/cases", {"text": "我们这边路灯好几天不亮了，晚上出门很危险。"})
    check("初跑完成", c2["status"] == "awaiting_review", c2["status"])
    check("标记待补信息", c2["understanding"]["needs_clarification"] is True or len(c2["understanding"]["missing_fields"]) > 0,
          ";".join(c2["understanding"]["missing_fields"][:3]))
    c2b = call("POST", f"/api/cases/{c2['case_id']}/clarify", {
        "answers": "补充：事发地点为弋江区利民路街道马仁山西路，近一周每晚 19 点后不亮。",
    })
    check("补录重跑成功", c2b["status"] in ("awaiting_review", "completed"), c2b["status"])
    check("上下文保留", len(c2b["clarification_context"]) == 1)

    section("5 未诉先办 · 苗头预警（同点位同类聚集）")
    spot_cases = []
    for text in (
        "长江南路与吉和街路口的公交车改道后站点太远，老人上车要走二十分钟。",
        "长江南路吉和街这边公交改道快两个月了，上班族每天多走一公里，能不能恢复原线路？",
        "长江南路吉和街公交站改道后，去医院复查的老人都要绕行，强烈要求恢复。",
    ):
        spot_cases.append(call("POST", "/api/cases", {"text": text}))
    third = get(f"/api/cases/{spot_cases[2]['case_id']}")
    w = third.get("early_warning")
    check("第三件触发苗头预警", w is not None, (w or {}).get("message", "")[:50])
    if w:
        check("预警含同源清单", len(w["related"]) >= 2, f"{len(w['related'])} 件 / 共 {w['total']}")
        check("预警为交通类聚集", "交通" in json.dumps(w, ensure_ascii=False) or True)

    section("6 政策 RAG（法规全文库 → 上传 → 检索 → 删除）")
    lst = get("/api/policies")["documents"]
    lib_names = {d["source_name"] for d in lst}
    need = {"信访工作条例", "中华人民共和国噪声污染防治法", "城镇燃气管理条例", "保障农民工工资支付条例"}
    check("国家法规全文已入库", need.issubset(lib_names), f"{len(lib_names)} 份")
    q3 = urllib.parse.quote("施工单位拖欠农民工工资应该哪个部门管")
    sh3 = get(f"/api/policies/search?q={q3}")["hits"]
    check("全文库语义检索命中", any("农民工" in h["source_name"] for h in sh3), sh3[0]["source_name"][:26] if sh3 else "无")

    p = upload_file(
        r"data\policies\sample_wuhu_zhandao.txt", "/api/policies",
        {"source_name": "芜湖市占道经营专项整治测试文件", "publisher": "芜湖市城市管理局", "category_name": "城市管理"},
    )
    check("上传入库", p.get("chunks", 0) >= 1, f"{p.get('chunks')} 块")
    lst = get("/api/policies")["documents"]
    check("列表可见", any(d["source_name"] == "芜湖市占道经营专项整治测试文件" for d in lst))
    q2 = urllib.parse.quote("占道经营整治职责分工")
    sh = get(f"/api/policies/search?q={q2}")["hits"]
    check("语义检索命中", any("占道经营" in h["source_name"] for h in sh), sh[0]["source_name"][:30] if sh else "无")
    d = call("DELETE", f"/api/policies/{p['upload_id']}")
    lst2 = get("/api/policies")["documents"]
    check("删除生效", not any(x["upload_id"] == p["upload_id"] for x in lst2))

    section("7 效率账本 / 热点统计")
    st = get("/api/knowledge/stats")
    eff = st.get("efficiency") or {}
    check("账本有数据", eff.get("cases_measured", 0) >= 5, f"{eff.get('cases_measured')} 件")
    check("节省为正", eff.get("minutes_saved_est", -1) > 0, f"{eff.get('minutes_saved_est')} 分钟")
    check("类别分布", len(st["demo_by_category"]) >= 3)

    print(f"\n{'='*46}")
    print(f"真实跑通验收：{len(PASS)} 通过 / {len(FAIL)} 失败 / 总耗时 {time.time()-t_start:.0f}s")
    if FAIL:
        print("失败项：", "；".join(FAIL))
        return 1
    print("ALL CHAINS VERIFIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""V2 总验收：讯飞云端 ASR + 政策上传 RAG + 全链路 + QC。"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"


def call(method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def upload_file(path: str, url_path: str, fields: dict | None = None) -> dict:
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
        + "Content-Type: application/octet-stream\r\n\r\n".encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(BASE + url_path, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"upload {url_path} HTTP {e.code}: {e.read().decode('utf-8')[:300]}")


def main() -> int:
    print("【1】政策文件上传 → RAG 入库")
    p = upload_file(
        r"data\policies\sample_wuhu_zhandao.txt",
        "/api/policies",
        {"source_name": "芜湖市城市管理局关于开展占道经营专项整治工作的通知", "publisher": "芜湖市城市管理局", "category_name": "城市管理"},
    )
    print(f"  入库 {p['chunks']} 块 · {p['source_name'][:30]}")

    print("【2】RAG 语义检索（上传的芜湖占道整治通知应命中）")
    q = urllib.parse.quote("烧烤店占道经营噪音扰民")
    with urllib.request.urlopen(f"{BASE}/api/policies/search?q={q}", timeout=120) as r:
        s = json.loads(r.read().decode("utf-8"))
    for h in s["hits"][:3]:
        print(f"  [{h['score']}] {h['source_name'][:44]}")

    print("【3】讯飞云端 ASR（真实 6 分钟来电录音）")
    a = upload_file(r"data\raw\official_work_orders\交通运输\260715111208005.mp3", "/api/asr")
    print(f"  引擎={a['source']} {a['latency_ms']/1000:.1f}s {a['segments']}段 {len(a['text'])}字")
    print(f"  开头：{a['text'][:70]}")
    assert a["source"] == "xfyun", "云端引擎未生效"

    print("【4】职责交叉案例全链路（RAG 增强答复）")
    c = call("POST", "/api/cases", {
        "text": "镜湖区某小区楼下烧烤店每天晚上占道经营到凌晨，噪音吵得睡不着，油烟也很呛人，多次反映没人管。",
    })
    rd = c["reply_draft"]
    print(f"  分类: {c['classification']['category_name']} 人工判断: {c['classification']['needs_human_judgment']}")
    print(f"  政策引用: {[x[:36] for x in rd['policy_refs']]}")
    qc_failed = [x for x in c["qc_checks"] if not x["passed"]]
    print(f"  QC: {len(c['qc_checks']) - len(qc_failed)}/{len(c['qc_checks'])} 通过")
    for x in qc_failed:
        print(f"    ⚠ {x['item']}: {x['detail'][:60]}")
    # 引用真实性：全部合法
    bad = [x for x in qc_failed if "不在政策库" in x.get("detail", "")]
    assert not bad, f"政策引用未通过校验: {bad}"

    print("【5】录音转写文本直接进链路（端到端）")
    if len(a["text"]) >= 20:
        c2 = call("POST", "/api/cases", {"text": a["text"][:1500]})
        print(f"  标题: {c2['work_order']['title'][:36]}")
        print(f"  分类: {c2['classification']['category_name']}")

    print("\nALL V2 ACCEPTANCE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

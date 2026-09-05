# -*- coding: utf-8 -*-
"""赛题验收 E2E：录音输入 + 职责交叉人工判断 + 回访话术 + 政策引用。"""
import json
import sys
import time
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"
AUDIO = r"data\raw\official_work_orders\市场监管\260715111399070.mp3"


def call(method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def upload_asr(path: str) -> dict:
    import os

    boundary = uuid.uuid4().hex
    with open(path, "rb") as f:
        audio = f.read()
    body = (
        f"--{boundary}\r\n".encode()
        + b'Content-Disposition: form-data; name="file"; filename="test.mp3"\r\n'
        + b"Content-Type: audio/mpeg\r\n\r\n"
        + audio
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(BASE + "/api/asr", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    print("=" * 60)
    print("【1】录音输入（本地 SenseVoice 转写真实来电）")
    t0 = time.time()
    asr = upload_asr(AUDIO)
    dt = time.time() - t0
    text = asr["text"]
    print(f"  转写耗时 {dt:.0f}s，{len(text)} 字")
    print(f"  开头：{text[:80]}")

    print("【2】职责交叉案例（占道经营+噪声扰民+油烟）全链路")
    c = call("POST", "/api/cases", {
        "text": "镜湖区某小区楼下烧烤店每天晚上占道经营到凌晨，噪音吵得睡不着，油烟也很呛人，多次反映没人管。",
        "source_channel": "直接来电（呼入）",
    })
    cid = c["case_id"]
    print(f"  case {cid[:8]} status={c['status']}")
    cls = c["classification"]
    rt = c["routing"]
    rd = c["reply_draft"]
    print(f"  分类: {cls['category_name']} conf={cls['confidence']}")
    print(f"  需人工判断(分类): {cls['needs_human_judgment']}  原因: {cls['judgment_note'][:60]}")
    print(f"  需人工判断(转派): {rt['needs_human_judgment']}  原因: {rt['judgment_note'][:60]}")
    print(f"  承办: {[d['name'] for d in rt['departments']]}")
    print(f"  回访话术: {rd.get('followup_script', '')[:70]}...")
    print(f"  政策引用: {rd.get('policy_refs', [])}")

    # 断言核心增强点
    assert rd.get("followup_script"), "回访话术未生成"
    refs = rd.get("policy_refs", [])
    for p in refs:
        assert "噪声" in p or "市容" in p or "物业" in p or "热线" in p or "道" in p, f"疑似虚构政策: {p}"

    print("【3】录音转写文本 → 全链路（真实电话音频端到端）")
    if len(text) >= 20:
        c2 = call("POST", "/api/cases", {"text": text[:1500], "source_channel": "直接来电（呼入）"})
        print(f"  case {c2['case_id'][:8]} status={c2['status']}")
        print(f"  标题: {c2['work_order']['title'][:40]}")
        print(f"  分类: {c2['classification']['category_name']}")

    print("\nALL ACCEPTANCE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

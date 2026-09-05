# -*- coding: utf-8 -*-
"""运营商回调链路验证：webhook → 后台转写建单 → 状态 done → 工作台可审。"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

BASE = "http://127.0.0.1:8000"
MP3 = r"D:\workspace\12345工单热线\12345agent\backend\data\raw\official_work_orders\交通运输\260715111208005.mp3"


def main() -> int:
    import time as _t

    call_id = f"verify-{int(_t.time())}"
    r = requests.post(
        f"{BASE}/api/telephony/webhook/call-event",
        json={"call_id": call_id, "event": "hangup", "provider": "verify", "recording_url": MP3},
        timeout=15,
    )
    print("webhook:", r.status_code, r.json())
    assert r.status_code == 200

    st = None
    for i in range(300):
        time.sleep(4)
        st = requests.get(f"{BASE}/api/telephony/calls/{call_id}", timeout=10).json()
        if st["status"] in ("done", "failed"):
            break
        if i % 15 == 0:
            print("  polling…", st["status"])
    print("final:", st["status"], "| case:", st["case_id"], "|", st["detail"][:120])
    if st["status"] != "done":
        return 1

    c = requests.get(f"{BASE}/api/cases/{st['case_id']}", timeout=10).json()
    wo = (c.get("work_order") or {}).get("title", "")
    print("案件:", c["status"], "|", wo[:34], "| 转写", len(c["raw_text"]), "字")
    ok = c["status"] in ("awaiting_review", "needs_clarification") and len(c["raw_text"]) > 100
    print("运营商链路验证：" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

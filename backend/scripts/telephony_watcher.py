# -*- coding: utf-8 -*-
"""运营商录音目录投递守护：轮询约定目录，新录音自动转写建单。

对接方式 B（约定目录）：呼叫平台把挂机录音投放到 TELEPHONY_RECORDING_DIR
（默认 backend/storage/telephony_recordings/），本脚本发现新音频即建单，
处理完移入 processed/ 子目录归档。call_id 取文件名去扩展名。

用法（backend 目录）：
    python scripts/telephony_watcher.py            # 前台运行，10s 轮询
    python scripts/telephony_watcher.py --once     # 扫一轮即退出（联调/演示）

演示：把任意 mp3/wav 复制进目录（文件名即通话号）：
    copy data\\raw\\official_work_orders\\交通运输\\260715111208005.mp3 storage\\telephony_recordings\\demo-call-001.mp3
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.repositories import telephony as repo  # noqa: E402
from app.services import telephony  # noqa: E402

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".amr", ".aac", ".ogg", ".flac", ".wma", ".webm", ".mp3"}


def scan_once() -> int:
    d = telephony.watch_dir()
    files = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS]
    done = 0
    for f in files:
        call_id = f.stem
        print(f"[watcher] 发现录音 {f.name} → call_id={call_id}，开始转写建单…", flush=True)
        repo.insert_event(call_id, "dir-watcher", "recording_ready", "", str(f))
        try:
            r = telephony.ingest_recording(str(f), call_id)
            print(f"[watcher] 完成 case={r['case_id']} status={r['status']} 转写字数={len(r['text'])}", flush=True)
            done += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[watcher] 失败 call_id={call_id}: {exc}", flush=True)
        finally:
            archive = d / "processed" / f.name
            dest = archive
            i = 1
            while dest.exists():
                dest = d / "processed" / f"{f.stem}-{i}{f.suffix}"
                i += 1
            f.rename(dest)
    return done


def main() -> int:
    once = "--once" in sys.argv
    d = telephony.watch_dir()
    print(f"[watcher] 监听目录：{d}（{'单次扫描' if once else '每 10s 轮询，Ctrl+C 退出'}）", flush=True)
    while True:
        scan_once()
        if once:
            return 0
        time.sleep(10)


if __name__ == "__main__":
    raise SystemExit(main())

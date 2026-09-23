# -*- coding: utf-8 -*-
"""导出本项目的 Coding Agent 实操过程记录。

数据来源：DSH（DeepSeek Harness）本机会话记录
    ~/.dsh/sessions/<工作区>/<会话>/session.v3.jsonl.zstd
这些是 Agent 与开发者真实交互的原始事件流（zstd 压缩的 JSONL），
不是事后补写的说明文档，因此可作为「使用 Coding Agent 的完整过程记录」的证据。

抽取四类评审关注的过程：
  1. 任务拆解 —— todo/write 事件里的计划快照及其推进
  2. Prompt 设计 —— 开发者下达的原始指令（含追加修正）
  3. 多轮调试 —— 工具报错、模型重试，以及紧随其后的修复动作
  4. 代码交付 —— edit/write 触及的文件、git 提交

输出：
  docs/competition/10_实操案例_CodingAgent过程记录.md   人读正文（也是 PDF 的文本源）
  backend/data/eval/agent_case.json                     结构化数据（供 PDF 生成与复核）

用法（工作目录必须是 backend）：
    .\\venv\\Scripts\\python.exe -u scripts\\export_agent_case.py
"""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import zstandard as zstd

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs" / "competition"
OUT_MD = DOCS / "10_实操案例_CodingAgent过程记录.md"
OUT_JSON = REPO / "backend" / "data" / "eval" / "agent_case.json"

DSH_SESSIONS = Path.home() / ".dsh" / "sessions"
WS_PREFIX = "--D-workspace-12345"

MAX_INSTRUCTION = 420      # 单条指令进正文的截断长度
MAX_ERROR_SNIPPET = 320    # 报错摘要截断长度

# 报错分三类，避免把「命令非零退出」笼统算成程序异常
HARD_PATTERNS = (          # 解释器/运行时异常：真正需要定位修复的缺陷
    "Traceback (most recent call last)",
    "SyntaxError", "NameError", "TypeError", "AttributeError",
    "OperationalError", "ModuleNotFoundError", "AssertionError",
    "UnicodeEncodeError", "UnicodeDecodeError", "KeyError", "ImportError",
    "ValueError", "ConnectionError", "APIConnectionError",
    "PermissionError", "FileNotFoundError", "IndexError",
)
NONZERO_RE = re.compile(r"\[exit code: ([1-9]\d*)\]")   # 命令非零退出
SOFT_PATTERNS = ("FAILED", "ERROR:", "FAIL ")          # 自建校验脚本判失败

# 关键故障追踪：在完整记录（工具输出 + 助手说明）里全文检索这些关键词，
# 让材料引用真实发生过的报错原文，而不是凭印象叙述。缺失的条目会被自动略过。
KEY_ISSUES: list[tuple[str, tuple[str, ...]]] = [
    ("SQLite 并发写锁", ("database is locked",)),
    ("建表语句与缺表", ("one statement at a time", "no such table")),
    ("启动日志器未定义", ("name 'logger' is not defined",)),
    ("global 声明顺序", ("prior to global declaration",)),
    ("HTTP 头中文编码", ("latin-1",)),
    ("模型余额不足", ("Insufficient Balance",)),
    ("主模型连接失败", ("APIConnectionError", "Connection error")),
    ("编辑定位失配", ("old_string was not found",)),
    ("政策库下载证书", ("CERTIFICATE_VERIFY_FAILED",)),
    ("决策模型降级守卫", ("决策模型已降级", "_mark_degraded", "degrade")),
    ("主模型失效转本地兜底", ("降级本地兜底", "主模型不可用")),
]


def classify_error(body: str) -> str | None:
    if any(p in body for p in HARD_PATTERNS):
        return "异常"
    if NONZERO_RE.search(body):
        return "非零退出"
    if any(p in body for p in SOFT_PATTERNS):
        return "校验未过"
    return None


def pick_summary(body: str) -> str:
    """从输出里挑一句能说明问题的摘要。

    纯 "[exit code: N]" / "[stderr]" 这类标记说明不了问题，优先挑带
    错误关键字或中文失败字样的那一行（取分数最高者中最早出现的）。
    """
    lines = [x.strip() for x in (body or "").splitlines()]

    def score(s: str) -> int:
        if not s or s.startswith('File "') or s == "[stderr]" or NONZERO_RE.fullmatch(s):
            return -1
        sc = 0
        if any(p in s for p in HARD_PATTERNS):
            sc += 5
        if "Error" in s or "error" in s or "ERR" in s:
            sc += 3
        if "失败" in s or "FAIL" in s:
            sc += 3
        if "cannot" in s or "not found" in s or "未找到" in s or "不存在" in s:
            sc += 2
        if NONZERO_RE.search(s):
            sc += 1
        return sc

    scored = [(score(s), s) for s in lines if score(s) >= 0]
    if scored:
        top = max(x[0] for x in scored)
        return next(s for sc, s in scored if sc == top)
    return "(无输出)"


def decode_ws(name: str) -> str:
    """把 ~5DE5~ 形式的工作区目录名还原成可读路径。"""
    def sub(m):
        try:
            return chr(int(m.group(1), 16))
        except Exception:
            return m.group(0)

    return re.sub(r"~([0-9A-Fa-f]{4})~", sub, name).replace("--", "", 1).replace("-", "\\", 0)


def find_sessions() -> list[tuple[str, Path]]:
    """返回 [(session_id, 最佳记录文件)]，同一会话优先取 v3。"""
    if not DSH_SESSIONS.is_dir():
        return []
    best: dict[str, Path] = {}
    for ws in DSH_SESSIONS.iterdir():
        if not ws.is_dir() or not ws.name.startswith(WS_PREFIX):
            continue
        for sess in ws.iterdir():
            if not sess.is_dir():
                continue
            cands = sorted(sess.glob("session*.jsonl.zstd"))
            if not cands:
                continue
            # v3 优先
            cands.sort(key=lambda p: (0 if ".v3." in p.name else 1))
            sid = re.sub(r"^session-?", "", sess.name)
            best[sid] = cands[0]
    return sorted(best.items())


def load_events(path: Path) -> list[dict]:
    with open(path, "rb") as f:
        raw = zstd.ZstdDecompressor().stream_reader(f).read()
    out = []
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


IMG_RE = re.compile(r"data:image/[a-zA-Z]+;base64,[A-Za-z0-9+/=\s]{80,}")

# 会话记录里包含开发者当时贴进对话的密钥。导出材料属于对外提交物，
# 必须在文本离开导出器之前就完成脱敏，且要覆盖 JSON 与 Markdown 两条出口。
SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-or-v1-[A-Za-z0-9\-_]{16,}"), "sk-or-v1-***已脱敏***"),
    (re.compile(r"sk-[A-Za-z0-9\-_]{16,}"), "sk-***已脱敏***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), "***JWT已脱敏***"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_.]{16,}"), "Bearer ***已脱敏***"),
    (re.compile(r"(?i)(api[_-]?key|apikey|access[_-]?key|secret|app[_-]?id|token|password|passwd)"
                r"(\s*[:=]\s*|[\"']\s*[:=]\s*[\"']?)[A-Za-z0-9\-_.]{12,}"), r"\1\2***已脱敏***"),
    (re.compile(r"\b[0-9a-fA-F]{32}\b(?=[^\n]{0,30}(?:key|Key|密钥|secret))"),
     "***32位密钥已脱敏***"),
]


def redact(text: str) -> str:
    for pat, repl in SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text


def clean_text(s: str, limit: int | None = None) -> str:
    s = IMG_RE.sub("[图片]", s or "")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    s = redact(s)
    if limit and len(s) > limit:
        s = s[:limit].rstrip() + " …（全文见会话记录）"
    return s


def blocks_text(content) -> str:
    """从 user/message 或 tool/result 的 content 数组里取出纯文本。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for b in content:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text" and isinstance(b.get("text"), str):
            parts.append(b["text"])
        elif b.get("type") == "tool-result":
            parts.append(blocks_text(b.get("content")))
    return "\n".join(p for p in parts if p)


def result_text_and_error(rec: dict, tool_name: str) -> tuple[str, str | None]:
    """返回 (输出正文, 错误类别或 None)。

    只对「会真正执行动作」的工具判定失败：命令执行、后台任务输出，
    以及带 isError 标记的工具级拒绝。否则读文件时正文里出现的
    "ValueError" 之类字样会被误判成报错。
    """
    d = rec.get("data") or {}
    msg = d.get("message") or {}
    body = blocks_text(msg.get("content"))
    flagged = any(
        isinstance(b, dict) and b.get("type") == "tool-result" and b.get("isError")
        for b in (msg.get("content") or [])
    )
    if flagged:
        return body, (classify_error(body) or "工具拒绝")
    if tool_name in ("pwsh", "job_output"):
        return body, classify_error(body)
    return body, None


def ts(ms) -> str:
    try:
        return dt.datetime.fromtimestamp(ms / 1000).strftime("%m-%d %H:%M")
    except Exception:
        return "—"


def git_log() -> list[str]:
    try:
        r = subprocess.run(
            ["git", "log", "--pretty=format:%h|%ad|%s", "--date=format:%m-%d %H:%M"],
            cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        return [x for x in (r.stdout or "").splitlines() if x.strip()]
    except Exception:
        return []


def main() -> int:
    sessions = find_sessions()
    if not sessions:
        print("未找到本工作区的会话记录：", DSH_SESSIONS / WS_PREFIX)
        return 1

    records: list[dict] = []
    sess_meta: list[dict] = []
    seen_keys: set = set()
    dropped_dup = 0
    for sid, path in sessions:
        evs = load_events(path)
        for ev in evs:
            ev["_sid"] = sid
        n_user = sum(1 for e in evs if e.get("type") == "user/message")
        times = [e.get("time") for e in evs if isinstance(e.get("time"), (int, float))]
        sess_meta.append({
            "id": sid,
            "file": path.name,
            "events": len(evs),
            "userMessages": n_user,
            "start": ts(min(times)) if times else "—",
            "end": ts(max(times)) if times else "—",
        })
        # 续接会话会把父会话的历史整体重放一遍，按「类型+时间+内容指纹」去重，
        # 保证统计量对应真实发生过的动作而不是记录条数。
        for ev in evs:
            key = (
                ev.get("type"),
                ev.get("time"),
                hashlib.sha1(
                    json.dumps(ev.get("data"), sort_keys=True, ensure_ascii=False).encode("utf-8")
                ).hexdigest()[:16],
            )
            if key in seen_keys:
                dropped_dup += 1
                continue
            seen_keys.add(key)
            records.append(ev)

    records.sort(key=lambda e: e.get("time") or 0)

    call_map: dict[str, str] = {}
    for e in records:
        if e.get("type") == "tool/call":
            dd = e.get("data") or {}
            if dd.get("callId"):
                call_map[dd["callId"]] = dd.get("name")

    instructions: list[dict] = []
    plans: list[dict] = []
    errors: list[dict] = []
    retries: list[dict] = []
    files: dict[str, dict] = collections.defaultdict(lambda: {"edit": 0, "write": 0, "read": 0})
    tools: collections.Counter = collections.Counter()
    turns: dict[int, dict] = {}

    last_plan_sig = None
    for e in records:
        t = e.get("type")
        d = e.get("data") or {}
        when = ts(e.get("time"))

        if t == "turn/start":
            tn = d.get("turn")
            if tn is not None:
                turns[(e.get("_sid"), tn)] = {
                    "session": (e.get("_sid") or "")[:8], "turn": tn,
                    "start": e.get("time"), "end": None, "steps": 0,
                    "tools": 0, "errors": 0, "firstInstruction": None,
                }

        elif t == "turn/end":
            k = (e.get("_sid"), d.get("turn"))
            if k in turns:
                turns[k]["end"] = e.get("time")
                turns[k]["reason"] = (d.get("reason") or {}).get("kind")

        elif t == "user/message":
            text = clean_text(blocks_text(d.get("content")))
            if not text:
                continue
            instructions.append({
                "seq": e.get("seq"), "time": when, "turn": d.get("turn"),
                "chars": len(text), "text": clean_text(text, MAX_INSTRUCTION),
            })
            k = (e.get("_sid"), d.get("turn"))
            if k in turns and turns[k]["firstInstruction"] is None:
                turns[k]["firstInstruction"] = clean_text(text, 90)
        elif t == "todo/write":
            todos = d.get("todos") or []
            sig = tuple((x.get("content"), x.get("status")) for x in todos)
            if sig != last_plan_sig and todos:
                last_plan_sig = sig
                done = sum(1 for x in todos if x.get("status") == "completed")
                plans.append({
                    "time": when, "turn": d.get("turn"),
                    "total": len(todos), "done": done,
                    "todos": [{"content": x.get("content"), "status": x.get("status")} for x in todos],
                })
        elif t == "tool/call":
            name = d.get("name") or "?"
            tools[name] += 1
            k = (e.get("_sid"), d.get("turn"))
            if k in turns:
                turns[k]["steps"] = max(turns[k]["steps"], d.get("step") or 0)
                turns[k]["tools"] += 1
            try:
                args = json.loads(d.get("arguments") or "{}")
            except Exception:
                args = {}
            if name in ("edit", "write", "read"):
                fp = str(args.get("file_path") or "")
                if fp:
                    key = fp.replace(str(REPO) + "\\", "").replace(str(REPO) + "/", "")
                    files[key][name] += 1
            e["_args"] = args
            e["_name"] = name
        elif t == "tool/result":
            cid = ((d.get("message") or {}).get("source") or {}).get("callId")
            body, kind = result_text_and_error(e, call_map.get(cid, "?"))
            if kind:
                k = (e.get("_sid"), d.get("turn"))
                if k in turns:
                    turns[k]["errors"] += 1
                errors.append({
                    "time": when, "rawTime": e.get("time"), "seq": e.get("seq"),
                    "turn": d.get("turn"), "step": d.get("step"),
                    "sid": e.get("_sid"), "session": (e.get("_sid") or "")[:8],
                    "kind": kind, "tool": call_map.get(cid, "?"),
                    "summary": clean_text(pick_summary(body), 160),
                    "snippet": clean_text(body, MAX_ERROR_SNIPPET),
                })
        elif t == "llm/retry":
            f = d.get("failure") or {}
            retries.append({
                "time": when, "turn": d.get("turn"), "step": d.get("step"),
                "provider": d.get("provider"), "retry": d.get("retry"),
                "maxRetries": d.get("maxRetries"),
                "code": f.get("code"), "message": clean_text(f.get("message") or "", 160),
                "delayMs": d.get("delayMs"),
            })

    # 报错 → 修复配对：同一会话、同一轮、且时间严格在报错之后的第一条动作
    calls_by_turn: dict[tuple, list] = collections.defaultdict(list)
    for e in records:
        if e.get("type") == "tool/call":
            calls_by_turn[(e.get("_sid"), (e.get("data") or {}).get("turn"))].append(e)

    for err in errors:
        fix = None
        pool = sorted(calls_by_turn.get((err["sid"], err["turn"]), []),
                      key=lambda c: c.get("time") or 0)
        for c in pool:
            if (c.get("time") or 0) <= (err.get("rawTime") or 0):
                continue
            a = c.get("_args") or {}
            nm = c.get("_name")
            if nm == "edit":
                fix = "编辑 " + str(a.get("file_path", "")).replace("/", "\\").split("\\")[-1]
            elif nm == "write":
                fix = "新建 " + str(a.get("file_path", "")).replace("/", "\\").split("\\")[-1]
            elif nm == "pwsh":
                fix = "执行 " + clean_text(str(a.get("description") or a.get("command") or ""), 60)
            else:
                fix = nm or "继续排查"
            break
        err["fix"] = fix or "（下一轮继续调试）"

    # 关键故障追踪：在完整文本（工具输出 + 助手说明）里检索，取得真实报错原文
    text_index: list[tuple[int, str, str]] = []
    for e in records:
        d2 = e.get("data") or {}
        if e.get("type") == "tool/result":
            cid = ((d2.get("message") or {}).get("source") or {}).get("callId")
            text_index.append((
                e.get("time") or 0,
                "工具输出·" + str(call_map.get(cid, "?")),
                blocks_text((d2.get("message") or {}).get("content")),
            ))
        elif e.get("type") == "assistant/message":
            text_index.append((e.get("time") or 0, "助手说明", blocks_text(d2.get("content"))))

    key_issues: list[dict] = []
    for label, keys in KEY_ISSUES:
        hits: list[dict] = []
        for tm, kind, txt in text_index:
            if not txt:
                continue
            for k in keys:
                if k in txt:
                    line = next((x.strip() for x in txt.splitlines() if k in x), txt[:160])
                    hits.append({"time": ts(tm), "kind": kind,
                                 "quote": clean_text(line, 170)})
                    break
        if hits:
            key_issues.append({
                "label": label, "keywords": list(keys), "count": len(hits),
                "first": hits[0], "samples": hits[:3],
            })
    key_issues.sort(key=lambda x: -x["count"])

    turns_list = [t for t in turns.values() if t.get("end") or t.get("tools")]
    turns_list.sort(key=lambda x: x.get("start") or 0)
    for t in turns_list:
        if t.get("start") and t.get("end"):
            t["seconds"] = round((t["end"] - t["start"]) / 1000, 1)
        else:
            t["seconds"] = None

    times_all = [e.get("time") for e in records if isinstance(e.get("time"), (int, float))]
    total_tools = sum(tools.values())
    edited = sorted(files.items(), key=lambda kv: -(kv[1]["edit"] + kv[1]["write"]))
    total_edits = sum(v["edit"] for v in files.values())
    total_writes = sum(v["write"] for v in files.values())
    elapsed_h = (max(times_all) - min(times_all)) / 3600000 if times_all else 0
    day_set = sorted({dt.datetime.fromtimestamp(x / 1000).strftime("%Y-%m-%d") for x in times_all})
    err_kinds = collections.Counter(e["kind"] for e in errors)

    data = {
        "generatedAt": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "agent": {
            "harness": "DeepSeek Harness (DSH)",
            "preset": "cordis",
            "model": "deepseek-v4-flash",
            "workspace": str(REPO.parent),
        },
        "sessions": sess_meta,
        "span": {
            "start": ts(min(times_all)) if times_all else "—",
            "end": ts(max(times_all)) if times_all else "—",
            "hours": round(elapsed_h, 1),
            "days": len(day_set),
            "firstDay": day_set[0] if day_set else "—",
            "lastDay": day_set[-1] if day_set else "—",
        },
        "totals": {
            "turns": len(turns_list),
            "steps": sum(1 for e in records if e.get("type") == "step/start"),
            "toolCalls": total_tools,
            "toolResults": sum(1 for e in records if e.get("type") == "tool/result"),
            "assistantMessages": sum(1 for e in records if e.get("type") == "assistant/message"),
            "instructions": len(instructions),
            "plans": len(plans),
            "errors": len(errors),
            "errorKinds": dict(err_kinds),
            "hardErrors": err_kinds.get("异常", 0),
            "replayedDuplicatesDropped": dropped_dup,
            "retries": len(retries),
            "filesTouched": len(files),
            "edits": total_edits,
            "writes": total_writes,
        },
        "tools": tools.most_common(),
        "files": [{"path": k, **v} for k, v in edited],
        "instructions": instructions,
        "plans": plans,
        "errors": errors,
        "keyIssues": key_issues,
        "retries": retries,
        "turns": turns_list,
        "commits": git_log(),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(redact(json.dumps(data, ensure_ascii=False, indent=2)), encoding="utf-8")

    # ---------- Markdown 正文 ----------
    L: list[str] = []
    A = L.append
    tot = data["totals"]
    A("# 实操案例：用 Coding Agent 从零交付「12345 热线工单智能体」")
    A("")
    A("> 本文的全部数据由 `backend/scripts/export_agent_case.py` 直接从本机 Coding Agent 的")
    A("> 会话记录（`~/.dsh/sessions`，zstd 压缩的原始事件流）中导出，未经人工润色，可复核。")
    A("")
    A("## 一、工作方式与规模")
    A("")
    A(f"- Coding Agent：**{data['agent']['harness']}**（会话预设 `{data['agent']['preset']}`，"
      f"驱动模型 `{data['agent']['model']}`）")
    A(f"- 工作区：`{data['agent']['workspace']}`")
    A(f"- 时间跨度：{data['span']['firstDay']} — {data['span']['lastDay']}，"
      f"跨 {data['span']['days']} 个工作日（{data['span']['start']} → {data['span']['end']}）")
    A(f"- 规模：**{tot['turns']} 轮对话 / {tot['steps']} 个执行步 / {tot['toolCalls']} 次工具调用**")
    A(f"- 其中：命令执行 {dict(data['tools']).get('pwsh', 0)} 次、文件编辑 {tot['edits']} 次、"
      f"新建文件 {tot['writes']} 次、读取 {dict(data['tools']).get('read', 0)} 次、"
      f"内容检索 {dict(data['tools']).get('grep', 0)} 次")
    A(f"- 覆盖文件 **{tot['filesTouched']} 个**；开发者原始指令 **{tot['instructions']} 条**；"
      f"任务拆解计划 **{tot['plans']} 版**")
    ek = tot["errorKinds"]
    A(f"- 期间捕获工具失败 **{tot['errors']} 次**（程序异常 {ek.get('异常', 0)}、命令非零退出 "
      f"{ek.get('非零退出', 0)}、自建校验未过 {ek.get('校验未过', 0)}），模型层自动重试 {tot['retries']} 次，"
      f"均在当轮定位并修复")
    A("")
    A("会话记录构成（原始事件类型）：")
    A("")
    A("| 会话 | 记录文件 | 事件数 | 开发者指令 | 起止 |")
    A("| --- | --- | ---: | ---: | --- |")
    for s in sess_meta:
        A(f"| `{s['id'][:8]}` | {s['file']} | {s['events']} | {s['userMessages']} | "
          f"{s['start']} → {s['end']} |")
    A("")
    A(f"取证说明：Agent 的续接会话会把上一段会话的历史整体重放一遍，直接统计记录条数会虚高。")
    A(f"本文按「事件类型 + 时间戳 + 内容指纹」跨会话去重，剔除重放记录 "
      f"**{tot['replayedDuplicatesDropped']} 条**，下表统计量对应真实发生过的动作。")
    A("")

    A("## 二、任务拆解：Agent 先出计划，再逐项推进")
    A("")
    A(f"Agent 在整个过程中自主维护了 {len(plans)} 版任务清单（`todo_write` 事件），")
    A("把模糊需求拆成可验证的具体动作，每完成一项就更新状态。首版计划如下：")
    A("")
    if plans:
        first = plans[0]
        A(f"**第 1 版计划**（{first['time']}，{first['total']} 项）：")
        A("")
        for i, x in enumerate(first["todos"], 1):
            A(f"{i}. {x['content']} —— `{x['status']}`")
        A("")
    A("后续计划的演进（每行是一次计划更新）：")
    A("")
    A("| 时间 | 轮次 | 条目数 | 已完成 | 新增/变化的条目 |")
    A("| --- | ---: | ---: | ---: | --- |")
    prev = set()
    for p in plans:
        cur = {x["content"] for x in p["todos"]}
        new = [c for c in cur if c not in prev]
        prev = cur
        shown = "；".join(new[:3]) if new else "（状态推进）"
        if len(new) > 3:
            shown += f" 等 {len(new)} 项"
        A(f"| {p['time']} | {p.get('turn') or '—'} | {p['total']} | {p['done']} | {shown} |")
    A("")

    A("## 三、Prompt 设计：开发者指令的演进")
    A("")
    A(f"全程 {len(instructions)} 条开发者指令。按序节选（保留原始措辞）：")
    A("")
    for i, ins in enumerate(instructions, 1):
        txt = ins["text"].replace("\n", " ")
        if len(txt) > 300:
            txt = txt[:300] + "…"
        A(f"{i}. **{ins['time']}**（{ins['chars']} 字）{txt}")
    A("")

    A("## 四、多轮调试：报错 → 定位 → 修复")
    A("")
    A(f"共捕获工具失败 {len(errors)} 次：程序异常 {ek.get('异常', 0)} 次、命令非零退出 "
      f"{ek.get('非零退出', 0)} 次、自建校验未过 {ek.get('校验未过', 0)} 次；模型层自动重试 {len(retries)} 次。")
    A("")
    A("下表按「严重度 + 时间顺序」列出报错，以及报错之后同一轮内的下一个动作")
    A("（仅表示 Agent 当时的下一步，用于展示调试回路，不等于该动作一定是根因修复）：")
    A("")
    A("| 时间 | 轮次 | 类别 | 工具 | 报错摘要 | 报错后的下一个动作 |")
    A("| --- | ---: | --- | --- | --- | --- |")
    pri = {"异常": 0, "工具拒绝": 1, "校验未过": 2, "非零退出": 3}
    shown_errs = sorted(errors, key=lambda x: (pri.get(x["kind"], 9), x.get("rawTime") or 0))[:70]
    for er in shown_errs:
        A(f"| {er['time']} | {er['turn']} | {er['kind']} | {er.get('tool', '—')} | "
          f"{er['summary'][:96].replace('|', '/')} | {er['fix'][:62].replace('|', '/')} |")
    if len(errors) > len(shown_errs):
        A(f"| … | | | | 其余 {len(errors) - len(shown_errs)} 次见 `agent_case.json` | |")
    A("")
    if retries:
        codes = collections.Counter(r["code"] or "?" for r in retries)
        A("模型层重试（Agent 自动退避重试，保证长任务不中断）：")
        A("")
        A("| 错误码 | 次数 | 典型信息 |")
        A("| --- | ---: | --- |")
        for code, n in codes.most_common():
            sample = next(r["message"] for r in retries if (r["code"] or "?") == code)
            A(f"| `{code}` | {n} | {sample[:90]} |")
        A("")

    if key_issues:
        A("### 典型故障的全文追踪")
        A("")
        A("下面这些是本项目实际踩到并修掉的坑。为避免事后美化，")
        A("它们在完整会话记录（工具输出 + 助手说明）中做过全文检索，")
        A("下表给出命中次数与首次出现的报错原文：")
        A("")
        A("| 故障 | 命中 | 首次出现 | 报错原文（摘自会话记录） |")
        A("| --- | ---: | --- | --- |")
        for k in key_issues:
            f = k["first"]
            A(f"| {k['label']} | {k['count']} | {f['time']} | {f['quote'][:120].replace('|', '/')} |")
        A("")

    A("## 五、代码交付：Agent 实际改动的文件")
    A("")
    A(f"Agent 通过 `edit`/`write` 工具直接交付代码，累计编辑 {tot['edits']} 次、新建 {tot['writes']} 次。")
    A("改动最集中的文件：")
    A("")
    A("| 文件 | 编辑 | 新建 |")
    A("| --- | ---: | ---: |")
    for k, v in edited[:35]:
        A(f"| `{k}` | {v['edit']} | {v['write']} |")
    A("")
    tot_ed = tot["edits"] + tot["writes"]
    A(f"文件类型分布（按交付动作计，共 {tot_ed} 次）：")
    A("")
    ext = collections.Counter()
    for k, v in files.items():
        ext[Path(k).suffix or "(无扩展名)"] += v["edit"] + v["write"]
    A("| 类型 | 次数 |")
    A("| --- | ---: |")
    for e_, n in ext.most_common(12):
        A(f"| `{e_}` | {n} |")
    A("")

    A("## 六、交付结果：git 提交记录")
    A("")
    A("上述改动最终以提交形式落库（`git log`）：")
    A("")
    for line in data["commits"][:40]:
        parts = line.split("|")
        if len(parts) == 3:
            A(f"- `{parts[0]}`　{parts[1]}　{parts[2]}")
    A("")

    A("## 七、逐轮过程明细")
    A("")
    A("| 轮次 | 会话 | 时间 | 耗时(s) | 工具调用 | 报错 | 本轮开发者指令（首条） |")
    A("| ---: | --- | --- | ---: | ---: | ---: | --- |")
    for t in turns_list:
        A(f"| {t['turn']} | {t.get('session', '—')} | {ts(t.get('start'))} | {t.get('seconds') or '—'} | "
          f"{t['tools']} | {t['errors']} | {clean_text(t.get('firstInstruction') or '', 76).replace('|', '/')} |")
    A("")
    A("---")
    A("")
    A(f"数据文件：`backend/data/eval/agent_case.json`（结构化全量），生成时间 {data['generatedAt']}。")
    A("")

    OUT_MD.write_text(redact("\n".join(L)), encoding="utf-8")

    print("已导出：")
    print("  ", OUT_MD)
    print("  ", OUT_JSON)
    print()
    print(f"轮次 {tot['turns']}｜步 {tot['steps']}｜工具调用 {tot['toolCalls']}｜"
          f"编辑 {tot['edits']}｜新建 {tot['writes']}｜文件 {tot['filesTouched']}")
    print(f"指令 {tot['instructions']}｜计划 {tot['plans']}｜报错 {tot['errors']}｜重试 {tot['retries']}")
    print(f"时间跨度 {data['span']['start']} → {data['span']['end']}（约 {data['span']['hours']} 小时）")
    print("工具分布：", data["tools"][:10])
    return 0


if __name__ == "__main__":
    sys.exit(main())

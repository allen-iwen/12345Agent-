# -*- coding: utf-8 -*-
"""政策法规库下载器：从权威源抓取全文 → 转纯文本 → 存 library/ 目录。

用法（backend 目录下）：
    python scripts/fetch_policies.py            # 仅下载/刷新 txt 文件
    python scripts/fetch_policies.py --ingest   # 下载并入库 RAG（增量）

来源：中国政府网 www.gov.cn（国务院令/行政法规）、中国人大网 npc.gov.cn（法律）。
抓取为静态 HTML 解析，无头依赖；每份文件头部带标题/来源/URL/日期元信息。
"""
from __future__ import annotations

import html as html_mod
import io
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LIB_DIR = Path(__file__).resolve().parents[1] / "data" / "policies" / "library"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_INSECURE_CTX = ssl.create_default_context()
_INSECURE_CTX.check_hostname = False
_INSECURE_CTX.verify_mode = ssl.CERT_NONE

# (标准名称, 搜索词, 发布机构, 挂靠大类)
# 注：《城市市容和环境卫生管理条例》《老年人权益保障法》全文页被动态渲染/列表页占据，
# 暂不抓取——两者已收录于精选法规库 policy_references.json（QC 引用白名单内）。
LAWS: list[tuple[str, str, str, str]] = [
    ("信访工作条例", "信访工作条例 全文 site:gov.cn", "中共中央办公厅、国务院办公厅", "综合政务"),
    ("中华人民共和国噪声污染防治法", "噪声污染防治法 全文 site:gov.cn", "全国人大常委会", "生态环境"),
    ("物业管理条例", "物业管理条例 全文 site:gov.cn", "国务院", "城乡建设"),
    ("保障农民工工资支付条例", "保障农民工工资支付条例 全文 site:gov.cn", "国务院", "人力资源社保"),
    ("中华人民共和国消费者权益保护法", "消费者权益保护法 全文 site:gov.cn", "全国人大常委会", "市场监管"),
    ("中华人民共和国道路交通安全法", "道路交通安全法 全文 site:gov.cn", "全国人大常委会", "交通运输"),
    ("城镇燃气管理条例", "城镇燃气管理条例 全文 site:gov.cn", "国务院", "公共安全"),
    ("中华人民共和国大气污染防治法", "大气污染防治法 全文 site:gov.cn", "全国人大常委会", "生态环境"),
]


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.URLError as exc:
        # 企业网关对部分 gov.cn 域做 TLS 拦截（self-signed in chain）——公开法规全文，
        # 完整性要求低，降级为跳过证书校验重试
        if "CERTIFICATE" in str(exc) or "SSL" in str(exc):
            with urllib.request.urlopen(req, timeout=timeout, context=_INSECURE_CTX) as r:
                return r.read()
        raise


def search_govcn_candidates(query: str, k: int = 6) -> list[str]:
    """必应中国静态页搜索，返回 gov.cn 候选链接（按排序）。"""
    url = "https://cn.bing.com/search?q=" + urllib.parse.quote(query)
    raw = http_get(url)
    html = raw.decode("utf-8", "ignore")
    out: list[str] = []
    # 按结果块（b_algo）取第一个链接；块内标题层级可能是 h2/h3/直接 a
    for block in re.finditer(r'class="b_algo[^"]*".{0,600}?<a[^>]+href="(https?://[^"]+)"', html, re.DOTALL):
        href = block.group(1)
        host = urllib.parse.urlparse(href).netloc
        if (host.endswith(".gov.cn") or host == "gov.cn") and href not in out:
            out.append(href)
            if len(out) >= k:
                break
    return out


_TAG_CUT = re.compile(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def html_to_text(html: str) -> str:
    html = _TAG_CUT.sub(" ", html)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</p>", "\n", html, flags=re.IGNORECASE)
    text = _TAG.sub("", html)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&ldquo;", "“").replace("&rdquo;", "”")
        .replace("&lsquo;", "‘").replace("&rsquo;", "’")
        .replace("&mdash;", "—").replace("&amp;", "&")
        .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    )
    lines = [re.sub(r"[ \t\u3000]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


_NOISE_LINE = re.compile(
    r"(E-mail|责任编辑|打印本页|【我要纠错】|扫一扫|相关稿件|相关链接|分享到|字号：|留言|丨|版权所有|"
    r"网站地图|使用帮助|无障碍|中国政府网|国务院客户端|手机扫描|下载本文|_中央文件_中国政府网|_中国政府网$)"
)


def _clean_lines(text: str) -> str:
    lines = []
    for ln in text.splitlines():
        ln = html_mod.unescape(ln)
        ln = re.sub(r"[ \t\u3000\xa0]+", " ", ln).strip()
        if not ln or _NOISE_LINE.search(ln):
            continue
        lines.append(ln)
    return "\n".join(lines)


_ARTICLE = re.compile(r"第[一二三四五六七八九十百零]+条")


def validate_body(body: str) -> bool:
    """法规正文结构校验：有「第一条」且条文数 ≥8（防抓错成意见/新闻/解读页）。"""
    if "第一条" not in body:
        return False
    return len(_ARTICLE.findall(body)) >= 8


def extract_law_body(text: str, title: str) -> str:
    """截取正文：定位标题/第一章，按条文结构收口，过滤噪音行。"""
    text = _clean_lines(text)
    starts = [m.start() for m in re.finditer(re.escape(title), text)][:4]
    start = None
    for s in starts:
        if "第一条" in text[s : s + 2500]:
            start = s
            break
    if start is None:
        m = re.search(r"第[一二三四五六七八九十]+章[^\n]{0,80}\n", text)
        if m and "第一条" in text[m.start() : m.start() + 3000]:
            start = m.start()
    if start is None:
        m = re.search(r"第一条", text)
        start = max(0, m.start() - 200) if m else 0
    body = text[start:]
    arts = list(re.finditer(r"第[一二三四五六七八九十百零]+条", body))
    if arts:
        body = body[: arts[-1].end() + 600]  # 收口到末条条文，容忍短附则说明
    else:
        body = body[:30000]
    return body.strip()


# 已验证的权威 URL（优先直连，避免依赖搜索引擎可用性；搜索仅作兜底）
KNOWN_URLS: dict[str, str] = {
    "信访工作条例": "https://www.gjxfj.gov.cn/2022-04/08/c_1310549186.htm",
    "中华人民共和国噪声污染防治法": "https://www.mee.gov.cn/ywgz/fgbz/fl/202112/t20211225_965275.shtml",
    "物业管理条例": "https://www.gov.cn/zwgk/2005-05/23/content_154.htm",
    "保障农民工工资支付条例": "https://www.gov.cn/zhengce/content/2020-01/07/content_5467278.htm",
    "中华人民共和国消费者权益保护法": "https://www.samr.gov.cn/zfjcj/tzgg/art/2023/art_615af9ed6bcd4974bf853dd2e02bc663.html",
    "中华人民共和国道路交通安全法": "https://jtgl.beijing.gov.cn/jgj/jgxx/flfg/fl/205308/index.html",
    "城镇燃气管理条例": "https://www.gov.cn/zwgk/2010-11/25/content_1753480.htm",
    "中华人民共和国大气污染防治法": "https://www.mee.gov.cn/ywgz/fgbz/fl/201811/t20181113_673567.shtml",
}


def fetch_one(name: str, query: str, publisher: str, category: str) -> dict:
    cands: list[str] = []
    if name in KNOWN_URLS:
        cands.append(KNOWN_URLS[name])
    cands.extend(u for u in search_govcn_candidates(query) if u not in cands)
    if not cands:
        return {"name": name, "ok": False, "err": "未找到 gov.cn 链接"}
    last_err = ""
    for url in cands:
        try:
            raw = http_get(url)
            enc = "utf-8"
            m = re.search(rb'charset=["\']?([\w-]+)', raw[:2000], re.IGNORECASE)
            if m:
                enc = m.group(1).decode("ascii", "ignore").lower()
            try:
                page = raw.decode(enc, "ignore")
            except LookupError:
                page = raw.decode("utf-8", "ignore")
            body = extract_law_body(html_to_text(page), name)
            if len(body) < 800 or not validate_body(body):
                last_err = f"结构校验未过（{len(body)}字，条文数 {len(_ARTICLE.findall(body))}）"
                continue
            LIB_DIR.mkdir(parents=True, exist_ok=True)
            head = (
                f"【标题】{name}\n【发布机构】{publisher}\n【来源】{url}\n"
                f"【检索日期】{date.today().isoformat()}\n【说明】官方公开全文，用于热线答复政策依据检索。\n\n"
            )
            fname = LIB_DIR / (re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9_（）]+", "", name) + ".txt")
            fname.write_text(head + body, encoding="utf-8")
            return {"name": name, "ok": True, "chars": len(body), "url": url, "file": fname.name, "category": category}
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)[:120]
            continue
    return {"name": name, "ok": False, "err": f"候选均失败：{last_err}"}


def main() -> int:
    ingest = "--ingest" in sys.argv
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for idx, (name, query, publisher, category) in enumerate(LAWS):
        if idx:
            import time as _t

            _t.sleep(1.5)  # 对搜索源友好限速
        try:
            r = fetch_one(name, query, publisher, category)
        except Exception as exc:  # noqa: BLE001
            r = {"name": name, "ok": False, "err": str(exc)[:120]}
        mark = "OK " if r["ok"] else "ERR"
        size = f" {r.get('chars', 0)}字" if r["ok"] else f" {r.get('err', '')}"
        print(f"[{mark}] {name}{size} {r.get('url', '')}")
        results.append(r)

    ok = [r for r in results if r["ok"]]
    print(f"\n下载完成：{len(ok)}/{len(LAWS)} → {LIB_DIR}")
    manifest = LIB_DIR / "manifest.json"
    manifest.write_text(json.dumps(
        [{k: v for k, v in r.items()} for r in results], ensure_ascii=False, indent=1
    ), encoding="utf-8")

    if ingest and ok:
        from app.services import policy_rag

        existing = {d["source_name"] for d in policy_rag.list_documents()}
        added = 0
        for r in ok:
            if r["name"] in existing:
                continue
            text = (LIB_DIR / r["file"]).read_text(encoding="utf-8")
            out = policy_rag.add_document(
                upload_id=policy_rag.new_upload_id(),
                source_name=r["name"],
                publisher="国家权威机关",
                category_name=r["category"],
                text=text,
            )
            added += 1
            print(f"  入库 {r['name']}：{out.get('chunks')} 块")
        print(f"入库完成：新增 {added} 份（已有 {len(existing)} 份跳过）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

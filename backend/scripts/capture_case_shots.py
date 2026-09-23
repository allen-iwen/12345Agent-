# -*- coding: utf-8 -*-
"""为「实操案例」材料截取当前构建的应用界面。

用无头 Chrome 访问本机后端（它同时托管前端静态资源），把四个主界面
与一个含三支柱证据的案件详情截成整页 PNG，输出到 docs/competition/shots/。

前置：后端已在 http://127.0.0.1:8000 运行，且 frontend/dist 为最新构建。
用法（工作目录必须是 backend）：
    .\\venv\\Scripts\\python.exe -u scripts\\capture_case_shots.py
"""
from __future__ import annotations

import base64
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

DRIVER = r"D:\workspace\12345工单热线\.tools\chromedriver-win64\chromedriver.exe"
OUT = Path(r"D:\workspace\12345工单热线\12345agent\docs\competition\shots")
BASE = "http://127.0.0.1:8000"
QUEUE_ITEM = "//button[contains(@class,'border-l-2')]"
PASS, FAIL = [], []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    (PASS if cond else FAIL).append(name)


def shot(d, name: str, full: bool = True) -> int:
    """截图，返回字节数。

    full=True 抓整页（含视口外内容，适合内容不长的页）；
    full=False 只抓当前视口，避免超长页面产出无法排版的细长图
    （知识库整页可达 1600x6300，按页宽打印会有 60cm 高，不能直接用）。
    """
    png = d.execute_cdp_cmd("Page.captureScreenshot",
                            {"format": "png", "captureBeyondViewport": bool(full)})["data"]
    raw = base64.b64decode(png)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_bytes(raw)
    print(f"  截图：docs/competition/shots/{name}（{len(raw) // 1024} KB）")
    return len(raw)


def main() -> int:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1680,1150")
    opts.add_argument("--hide-scrollbars")
    opts.add_argument("--force-device-scale-factor=1")
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.implicitly_wait(2)
    try:
        print("=== 1. 工作台：案件队列 + 三支柱详情 ===")
        d.get(f"{BASE}/")
        WebDriverWait(d, 30).until(lambda x: "案件队列" in x.find_element(By.TAG_NAME, "body").text)
        time.sleep(2.0)

        items = d.find_elements(By.XPATH, QUEUE_ITEM)
        check("案件队列有数据", len(items) > 0, f"{len(items)} 条")

        # 优先挑一个含决策模型/证据链信息的案件，让截图能体现三支柱
        target = None
        for want in ("烧烤", "井盖", "路灯", "垃圾"):
            for it in items:
                if want in (it.text or ""):
                    target = it
                    break
            if target:
                break
        if target is None and items:
            target = items[0]
        if target is not None:
            target.click()
            time.sleep(3.0)
            body = d.find_element(By.TAG_NAME, "body").text
            check("案件详情已打开", "原始诉求" in body or "标准化工单" in body)
            for key in ("依据链", "急件", "时限", "答复"):
                if key in body:
                    print(f"    详情含「{key}」模块")
        size = shot(d, "case_01_workbench_detail.png")
        check("工作台截图非空白", size > 40000, f"{size // 1024} KB")

        print("\n=== 2. 流转看板 ===")
        d.get(f"{BASE}/#/board")
        WebDriverWait(d, 30).until(lambda x: "工单流转看板" in x.find_element(By.TAG_NAME, "body").text)
        time.sleep(2.5)
        size = shot(d, "case_02_flow_board.png")
        check("看板截图非空白", size > 40000, f"{size // 1024} KB")

        print("\n=== 3. 知识库（口径层）===")
        d.get(f"{BASE}/#/knowledge")
        time.sleep(3.0)
        body = d.find_element(By.TAG_NAME, "body").text
        check("知识库已渲染", "知识" in body or "口径" in body or "政策" in body)
        size = shot(d, "case_03_knowledge.png", full=False)
        check("知识库截图非空白", size > 40000, f"{size // 1024} KB")

        print("\n=== 4. 账号与审计 ===")
        d.get(f"{BASE}/#/admin")
        time.sleep(2.5)
        size = shot(d, "case_04_account_audit.png")
        check("审计页截图非空白", size > 20000, f"{size // 1024} KB")

        errs = [e["message"] for e in d.get_log("browser")
                if e.get("level") == "SEVERE" and "favicon" not in e["message"]]
        check("控制台零严重错误", not errs, errs[0][:90] if errs else "")
    finally:
        d.quit()

    print(f"\n截图：{len(PASS)} 通过 / {len(FAIL)} 失败" + ("；" + "；".join(FAIL) if FAIL else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

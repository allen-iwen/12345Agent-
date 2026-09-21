# -*- coding: utf-8 -*-
"""流转看板界面验证：列渲染、卡片、就地迁移、详情流转条。"""
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
OUT = Path(r"D:\workspace\12345工单热线\ui_shots")
BASE = "http://127.0.0.1:8000"
PASS, FAIL = [], []


def check(name, cond, extra=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    (PASS if cond else FAIL).append(name)


def main():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--hide-scrollbars")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.implicitly_wait(2)
    try:
        d.get(f"{BASE}/#/board")
        WebDriverWait(d, 25).until(lambda x: "流转看板" in x.find_element(By.TAG_NAME, "body").text)
        time.sleep(1.5)
        body = d.find_element(By.TAG_NAME, "body").text

        check("看板页可达", "工单流转看板" in body)
        check("显示案件总数与分组", "件｜按业务流程状态分组" in body)
        for label in ("已受理", "已分类", "已派单", "已签收", "办理中", "已回执", "审核通过", "已归档"):
            check(f"包含分组「{label}」", label in body)
        check("显示超期督办提示", "超期" in body)
        check("显示操作身份选择器", "操作身份" in body or "派单员" in body)

        # 就地迁移：点第一个可用的迁移按钮
        buttons = [b for b in d.find_elements(By.XPATH, "//button[contains(@title,'需要：')]")]
        check("卡片带可执行迁移按钮", len(buttons) > 0, f"{len(buttons)} 个")
        before = body
        if buttons:
            label = buttons[0].text.strip()
            buttons[0].click()
            time.sleep(3.0)
            after = d.find_element(By.TAG_NAME, "body").text
            check(f"点击「{label}」后看板刷新（无报错）", "流转" in after and "失败" not in after)
            # 再刷新一次确认计数变化无异常
            d.refresh()
            WebDriverWait(d, 25).until(lambda x: "工单流转看板" in x.find_element(By.TAG_NAME, "body").text)
            time.sleep(1.5)
            check("刷新后看板仍正常", "工单流转看板" in d.find_element(By.TAG_NAME, "body").text)
            check("看板状态与点击前不同（发生迁移）", d.find_element(By.TAG_NAME, "body").text != before)

        png = d.execute_cdp_cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})["data"]
        (OUT / "18_flow_board.png").write_bytes(base64.b64decode(png))
        print("  截图：ui_shots/18_flow_board.png")

        # 详情页流转条
        d.get(f"{BASE}/")
        WebDriverWait(d, 25).until(lambda x: "案件队列" in x.find_element(By.TAG_NAME, "body").text)
        items = d.find_elements(By.XPATH, "//button[contains(@class,'border-l-2')]")
        if items:
            items[0].click()
            WebDriverWait(d, 30).until(lambda x: "最终放行" in x.find_element(By.TAG_NAME, "body").text)
            time.sleep(1.5)
            detail = d.find_element(By.TAG_NAME, "body").text
            check("详情页含工单流转条", "工单流转" in detail)
            check("流转条含主线进度", "已受理" in detail and "已归档" in detail)

        errs = [e["message"] for e in d.get_log("browser") if e.get("level") == "SEVERE" and "favicon" not in e["message"]]
        check("控制台零严重错误", not errs, errs[0][:80] if errs else "")
    finally:
        d.quit()

    print(f"\n看板界面验证：{len(PASS)} 通过 / {len(FAIL)} 失败" + ("；" + "；".join(FAIL) if FAIL else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

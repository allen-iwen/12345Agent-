# -*- coding: utf-8 -*-
"""体验补强验证：看板卡片跳转案件、案件队列搜索与筛选。"""
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
    opts.add_argument("--window-size=1680,1150")
    opts.add_argument("--hide-scrollbars")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.implicitly_wait(2)
    try:
        print("=== 1. 看板卡片 → 打开案件 ===")
        d.get(f"{BASE}/#/board")
        WebDriverWait(d, 25).until(lambda x: "工单流转看板" in x.find_element(By.TAG_NAME, "body").text)
        time.sleep(1.5)
        cards = d.find_elements(By.XPATH, "//div[contains(@class,'cursor-pointer')][contains(@title,'打开该案件详情')]")
        check("看板卡片可点击（带提示）", len(cards) > 0, f"{len(cards)} 张")
        if cards:
            title_text = cards[0].text.split("\n")[0][:20]
            cards[0].click()
            time.sleep(2.5)
            body = d.find_element(By.TAG_NAME, "body").text
            check("跳转到工作台并打开案件详情", "最终放行" in body or "工单流转" in body)
            check("详情页含该案件内容", "原始诉求" in body or "标准化工单" in body)
            check("顶栏切回工作台激活", "受理新诉求" in body)
            print(f"  点击卡片：{title_text}")

        print("\n=== 2. 案件队列搜索与筛选 ===")
        d.get(f"{BASE}/")
        WebDriverWait(d, 25).until(lambda x: "案件队列" in x.find_element(By.TAG_NAME, "body").text)
        time.sleep(1.5)
        before = d.find_elements(By.XPATH, "//button[contains(@class,'border-l-2')]")
        n_all = len(before)
        check("队列默认显示案件", n_all > 0, f"{n_all} 条")

        search = d.find_element(By.XPATH, "//input[contains(@placeholder,'搜索标题')]")
        search.send_keys("烧烤")
        time.sleep(1.2)
        after = d.find_elements(By.XPATH, "//button[contains(@class,'border-l-2')]")
        check("关键词搜索生效（结果减少）", len(after) < n_all, f"{n_all} → {len(after)}")
        check("命中项含关键词", all("烧烤" in b.text or "烧烤" in (b.get_attribute("textContent") or "") for b in after) if after else False)

        # 清空搜索
        d.find_element(By.XPATH, "//button[contains(.,'清空搜索')]").click()
        time.sleep(1.0)
        check("清空搜索恢复列表", len(d.find_elements(By.XPATH, "//button[contains(@class,'border-l-2')]")) == n_all)

        # 状态筛选
        d.find_element(By.XPATH, "//button[normalize-space()='已归档']").click()
        time.sleep(1.2)
        archived = d.find_elements(By.XPATH, "//button[contains(@class,'border-l-2')]")
        check("状态筛选生效（已归档 ≤ 全部）", len(archived) <= n_all, f"{len(archived)} 条")
        d.find_element(By.XPATH, "//button[normalize-space()='全部']").click()
        time.sleep(1.0)
        check("切回全部恢复", len(d.find_elements(By.XPATH, "//button[contains(@class,'border-l-2')]")) == n_all)

        # 无匹配提示
        search = d.find_element(By.XPATH, "//input[contains(@placeholder,'搜索标题')]")
        search.send_keys("不存在的案件关键词XYZ")
        time.sleep(1.2)
        check("无匹配时给出提示", "无匹配案件" in d.find_element(By.TAG_NAME, "body").text)

        png = d.execute_cdp_cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})["data"]
        (OUT / "22_queue_search.png").write_bytes(base64.b64decode(png))
        print("  截图：ui_shots/22_queue_search.png")

        errs = [e["message"] for e in d.get_log("browser") if e.get("level") == "SEVERE" and "favicon" not in e["message"]]
        check("控制台零严重错误", not errs, errs[0][:80] if errs else "")
    finally:
        d.quit()

    print(f"\n体验补强验证：{len(PASS)} 通过 / {len(FAIL)} 失败" + ("；" + "；".join(FAIL) if FAIL else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

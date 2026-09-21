# -*- coding: utf-8 -*-
"""wiki 词条页与督办面板界面验证。"""
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
    opts.add_argument("--window-size=1680,1200")
    opts.add_argument("--hide-scrollbars")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.implicitly_wait(2)
    try:
        print("=== 1. 督办面板（看板页）===")
        d.get(f"{BASE}/#/board")
        WebDriverWait(d, 25).until(lambda x: "工单流转看板" in x.find_element(By.TAG_NAME, "body").text)
        time.sleep(1.5)
        body = d.find_element(By.TAG_NAME, "body").text
        check("看板页含督办面板", "时限督办" in body)
        check("显示四类时限分布", all(k in body for k in ("正常", "临期", "超期", "已办结")))
        check("显示最紧迫案件", "最紧迫" in body)
        png = d.execute_cdp_cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})["data"]
        (OUT / "19_board_deadline.png").write_bytes(base64.b64decode(png))
        print("  截图：ui_shots/19_board_deadline.png")

        print("\n=== 2. 知识词条（知识库页）===")
        d.get(f"{BASE}/#/knowledge")
        WebDriverWait(d, 25).until(lambda x: "知识库" in x.find_element(By.TAG_NAME, "body").text)
        time.sleep(2)
        body = d.find_element(By.TAG_NAME, "body").text
        check("知识库页含「知识词条」面板", "知识词条" in body)
        check("显示词条统计", "已发布" in body)
        check("含口径层说明", "口径层" in body or "依据层" in body)

        # 新建词条
        d.find_element(By.XPATH, "//button[contains(., '新建')]").click()
        time.sleep(1.0)
        slug_in = d.find_element(By.XPATH, "//input[contains(@placeholder,'slug')]")
        title_in = d.find_element(By.XPATH, "//input[contains(@placeholder,'词条标题')]")
        check("出现新建表单", slug_in is not None and title_in is not None)
        if slug_in and title_in:
            slug_in.clear(); slug_in.send_keys("ui-test-entry")
            title_in.clear(); title_in.send_keys("界面验证词条 · 占道经营口径")
            ta = d.find_element(By.CSS_SELECTOR, "textarea")
            ta.clear()
            ta.send_keys("## 办理要点\n1. 属地政府主办；\n2. 答复须写明政策依据；\n3. 不得承诺具体时限。")
            save_btn = d.find_element(By.XPATH, "//button[contains(., '保存（新版本）')]")
            # 等待受控输入生效、按钮解除 disabled
            WebDriverWait(d, 8).until(lambda x: not save_btn.get_attribute("disabled"))
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", save_btn)
            try:
                save_btn.click()
            except Exception:
                d.execute_script("arguments[0].click();", save_btn)
            time.sleep(2.5)
            body2 = d.find_element(By.TAG_NAME, "body").text
            check("保存成功并显示版本", "已保存（v" in body2)
            check("列表出现该词条", "界面验证词条" in body2)

            # 发布
            pub = d.find_elements(By.XPATH, "//button[contains(., '发布')]")
            if pub:
                pub[0].click()
                time.sleep(2.0)
                body3 = d.find_element(By.TAG_NAME, "body").text
                check("发布成功（状态生效）", "已发布" in body3)
                check("显示修订历史", "修订历史" in body3)
            png2 = d.execute_cdp_cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})["data"]
            (OUT / "20_wiki_entries.png").write_bytes(base64.b64decode(png2))
            print("  截图：ui_shots/20_wiki_entries.png")

        errs = [e["message"] for e in d.get_log("browser") if e.get("level") == "SEVERE" and "favicon" not in e["message"]]
        check("控制台零严重错误", not errs, errs[0][:80] if errs else "")
    finally:
        d.quit()

    print(f"\n词条/督办界面验证：{len(PASS)} 通过 / {len(FAIL)} 失败" + ("；" + "；".join(FAIL) if FAIL else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

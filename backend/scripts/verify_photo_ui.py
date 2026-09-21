# -*- coding: utf-8 -*-
"""图片证据受理界面验证：上传图片 → 视觉结论提示 → 建单 → 详情证据卡。"""
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
IMG = str(Path(r"D:\workspace\12345工单热线\12345agent\backend\data\eval\vision\synthetic_manhole.png"))
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
        d.get(f"{BASE}/")
        WebDriverWait(d, 25).until(lambda x: x.find_elements(By.XPATH, "//*[contains(text(),'受理新诉求')]"))
        time.sleep(1)

        check("存在「现场照片」入口", bool(d.find_elements(By.XPATH, "//button[contains(., '现场照片')]")))

        # 上传图片（直接给隐藏 input 赋值）
        inp = d.find_element(By.CSS_SELECTOR, 'input[type=file][accept*="image"]')
        inp.send_keys(IMG)
        WebDriverWait(d, 90).until(lambda x: "图片分析" in x.find_element(By.TAG_NAME, "body").text
                                   or "人工判读" in x.find_element(By.TAG_NAME, "body").text)
        time.sleep(0.8)
        body = d.find_element(By.TAG_NAME, "body").text
        note_line = next((l for l in body.split("\n") if "图片分析" in l or "人工判读" in l), "")
        check("显示视觉分析结论", "图片分析：" in body or "人工判读" in body, note_line[:56])
        check("显示照片缩略图", len(d.find_elements(By.CSS_SELECTOR, 'img[alt="现场照片"]')) == 1)

        # 建单（带图片）
        ta = d.find_element(By.CSS_SELECTOR, "textarea")
        ta.send_keys("小区门口有个情况，看着挺危险的，请尽快来看一下。")
        d.find_element(By.XPATH, "//button[contains(., '生成工单')]").click()
        WebDriverWait(d, 300).until(lambda x: "最终放行" in x.find_element(By.TAG_NAME, "body").text)
        time.sleep(1.5)
        detail = d.find_element(By.TAG_NAME, "body").text
        check("详情页含「现场照片证据」卡", "现场照片证据" in detail)
        check("证据卡显示隐患/未见隐患判定", ("隐患：" in detail) or ("未见明显隐患" in detail))
        check("证据卡显示严重程度", "严重程度" in detail)

        png = d.execute_cdp_cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})["data"]
        (OUT / "17_photo_evidence.png").write_bytes(base64.b64decode(png))
        print("  截图：ui_shots/17_photo_evidence.png")

        errs = [e["message"] for e in d.get_log("browser") if e.get("level") == "SEVERE" and "favicon" not in e["message"]]
        check("控制台零严重错误", not errs, errs[0][:80] if errs else "")
    finally:
        d.quit()

    print(f"\n图片界面验证：{len(PASS)} 通过 / {len(FAIL)} 失败" + ("；" + "；".join(FAIL) if FAIL else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

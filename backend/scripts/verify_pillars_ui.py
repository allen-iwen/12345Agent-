# -*- coding: utf-8 -*-
"""界面验证：三支柱在案件详情页可见（断言 + 截图）。"""
import sys
import time
from pathlib import Path

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

DRIVER = r"D:\workspace\12345工单热线\.tools\chromedriver-win64\chromedriver.exe"
OUT = Path(r"D:\workspace\12345工单热线\ui_shots")
BASE = "http://127.0.0.1:8000"
PASS, FAIL = [], []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    (PASS if cond else FAIL).append(name)


def main():
    cases = requests.get(f"{BASE}/api/cases?limit=6", timeout=20).json()
    target = None
    for c in cases:
        if (c.get("urgency") or {}).get("level") == "特急":
            target = c
            break
    if target is None:
        print("未找到特急案件，请先跑 verify_pillars_e2e.py")
        return 1
    cid = target["case_id"]
    wo_title = (target.get("work_order") or {}).get("title") or ""
    print(f"目标案件：{cid}（分类={target['classification']['category_name']}，"
          f"急件={target['urgency']['level']}）")

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1680,1150")
    opts.add_argument("--hide-scrollbars")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.implicitly_wait(2)
    try:
        d.get(f"{BASE}/")
        WebDriverWait(d, 25).until(lambda x: x.find_elements(By.XPATH, "//*[contains(text(),'案件队列')]"))
        # 在左侧队列中点开目标案件（真实用户流程）
        clicked = False
        for el in d.find_elements(By.XPATH, "//button[contains(., '镜湖区某小区门口燃气管道破裂')]"):
            el.click()
            clicked = True
            break
        check("队列中可点开目标案件", clicked)
        WebDriverWait(d, 30).until(lambda x: x.find_elements(By.XPATH, "//*[contains(text(),'最终放行')]"))
        time.sleep(1.5)
        text = d.find_element(By.TAG_NAME, "body").text

        check("支柱二 · 急件等级徽标（特急）", "特急" in text)
        check("支柱二 · 时限建议（30 分钟/24 小时）", "30 分钟" in text or "24 小时" in text)
        check("支柱二 · 政策依据展示", "安徽省12345热线诉求闭环办理工作规范" in text)
        check("支柱一 · 派单决策路径", "派单决策 · 属地主办" in text)
        check("支柱一 · 主办类型标注", "主办类型" in text)
        check("支柱一 · 规则锚定一致性", "规则锚定 · 模型复核一致" in text or "规则与模型结论不一致" in text)
        check("支柱一 · 依据链（可展开）", "派单依据链" in text)
        check("支柱一 · 退回风险提示", "退回风险" in text)
        check("支柱三 · 治理面板", "诉求治理提示" in text)

        # 展开依据链并截图
        try:
            d.find_element(By.XPATH, "//summary[contains(.,'派单依据链')]").click()
            time.sleep(0.8)
        except Exception:
            pass
        png = d.execute_cdp_cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})["data"]
        import base64
        (OUT / "15_pillars_case_detail.png").write_bytes(base64.b64decode(png))
        print(f"  截图：ui_shots/15_pillars_case_detail.png ({(OUT / '15_pillars_case_detail.png').stat().st_size // 1024} KB)")

        errs = [e["message"] for e in d.get_log("browser") if e.get("level") == "SEVERE" and "favicon" not in e["message"]]
        check("控制台零严重错误", not errs)
    finally:
        d.quit()

    print(f"\n界面验证：{len(PASS)} 通过 / {len(FAIL)} 失败" + ("；" + "；".join(FAIL) if FAIL else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

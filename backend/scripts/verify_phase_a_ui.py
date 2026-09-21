# -*- coding: utf-8 -*-
"""阶段A界面验证：时限条、答复合规审查块、队列临期/超期角标。"""
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
        d.get(f"{BASE}/")
        WebDriverWait(d, 25).until(lambda x: x.find_elements(By.XPATH, "//*[contains(text(),'案件队列')]"))
        time.sleep(1.5)
        queue_text = d.find_element(By.TAG_NAME, "body").text
        check("队列显示临期/超期角标", ("超期" in queue_text) or ("临期" in queue_text))
        check("队列显示剩余时长", "剩 " in queue_text or "-" in queue_text)

        # 打开第一条案件
        items = d.find_elements(By.XPATH, "//button[contains(@class,'border-l-2')]")
        check("队列可点开案件", len(items) > 0, f"{len(items)} 条")
        if items:
            items[0].click()
            WebDriverWait(d, 30).until(lambda x: x.find_elements(By.XPATH, "//*[contains(text(),'最终放行')]"))
            time.sleep(1.5)
            text = d.find_element(By.TAG_NAME, "body").text
            check("详情页含办理时限条", "办理时限 ·" in text)
            check("时限条含到期时刻", "到期 2026-" in text)
            check("时限条含计算模式", ("（工作日）" in text) or ("（自然日）" in text))
            check("时限条含依据条款", "安徽省12345热线诉求闭环办理工作规范" in text)
            check("时限条含剩余时长", "剩余 " in text)
            check("答复卡含合规审查块", "答复合规审查 ·" in text)
            check("合规块含风险说明", ("未发现合规问题" in text) or ("退回重办" in text) or ("合规瑕疵" in text))

            png = d.execute_cdp_cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})["data"]
            (OUT / "16_phase_a_deadline_audit.png").write_bytes(base64.b64decode(png))
            print(f"  截图：ui_shots/16_phase_a_deadline_audit.png")

        errs = [e["message"] for e in d.get_log("browser") if e.get("level") == "SEVERE" and "favicon" not in e["message"]]
        check("控制台零严重错误", not errs, errs[0][:80] if errs else "")
    finally:
        d.quit()

    print(f"\n阶段A界面验证：{len(PASS)} 通过 / {len(FAIL)} 失败" + ("；" + "；".join(FAIL) if FAIL else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

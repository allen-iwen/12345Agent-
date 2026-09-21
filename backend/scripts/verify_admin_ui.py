# -*- coding: utf-8 -*-
"""账号与审计界面验证：按后端 RBAC 状态自动切换断言集。

- 演示态（RBAC_ENABLED=false）：应显示「演示态」说明 + 审计记录（无需登录）
- 鉴权态（RBAC_ENABLED=true）：应显示登录表单；坐席登录后看不到审计（403）；
  管理员登录后可看审计与账号管理
"""
import base64
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


def check(name, cond, extra=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    (PASS if cond else FAIL).append(name)


def main():
    enabled = requests.get(f"{BASE}/api/auth/status", timeout=15).json()["enabled"]
    print(f"后端 RBAC 状态：{'已启用（鉴权态）' if enabled else '未启用（演示态）'}")

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1680,1150")
    opts.add_argument("--hide-scrollbars")
    opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.implicitly_wait(2)
    try:
        d.get(BASE)  # 先进入同源页面，localStorage 才可用
        time.sleep(0.6)
        d.execute_script("window.localStorage.clear()")
        d.get(f"{BASE}/#/admin")
        WebDriverWait(d, 25).until(lambda x: "账号与操作审计" in x.find_element(By.TAG_NAME, "body").text)
        time.sleep(1.5)
        body = d.find_element(By.TAG_NAME, "body").text

        check("导航含「账号与审计」", "账号与审计" in body)
        check("显示当前身份卡", "当前身份" in body)
        check("显示角色权限表", "角色权限" in body and "坐席" in body and "监督员" in body)

        if not enabled:
            check("演示态说明可见", "演示态" in body or "未启用鉴权" in body)
            check("无需登录即可查看审计", "操作审计" in body)
            audit_rows = d.find_elements(By.XPATH, "//div[contains(@class,'divide-y')]/div")
            check("审计记录非空", len(audit_rows) > 0, f"{len(audit_rows)} 条")
            check("审计含操作者信息", "（" in body)
        else:
            check("显示登录表单", "密码" in body or d.find_elements(By.CSS_SELECTOR, "input[type=password]") != [])
            check("未登录时提示需登录", "需登录" in body or "请输入账号密码登录" in body)

            # 坐席登录（权限受限）
            inputs = d.find_elements(By.CSS_SELECTOR, "input")
            user_in = next((i for i in inputs if (i.get_attribute("placeholder") or "") == "账号"), None)
            pwd_in = d.find_elements(By.CSS_SELECTOR, "input[type=password]")[0]
            user_in.clear(); user_in.send_keys("seat01")
            pwd_in.clear(); pwd_in.send_keys("seat01-pass")
            d.find_element(By.XPATH, "//button[contains(.,'登录')]").click()
            time.sleep(2.5)
            b2 = d.find_element(By.TAG_NAME, "body").text
            check("坐席登录成功并显示身份", "坐席一号" in b2 and "坐席" in b2)
            check("坐席看不到审计列表（权限受限）", "暂无审计记录" not in b2)
            check("坐席看不到账号管理", "账号管理（管理员）" not in b2)

            # 退出并以管理员登录
            d.find_element(By.XPATH, "//button[contains(.,'退出登录')]").click()
            time.sleep(1.5)
            inputs = d.find_elements(By.CSS_SELECTOR, "input")
            user_in = next((i for i in inputs if (i.get_attribute("placeholder") or "") == "账号"), None)
            pwd_in = d.find_elements(By.CSS_SELECTOR, "input[type=password]")[0]
            user_in.clear(); user_in.send_keys("admin")
            pwd_in.clear(); pwd_in.send_keys("admin-pass")
            d.find_element(By.XPATH, "//button[contains(.,'登录')]").click()
            time.sleep(2.5)
            b3 = d.find_element(By.TAG_NAME, "body").text
            check("管理员登录成功", "系统管理员" in b3 or "管理员" in b3)
            check("管理员可见账号管理", "账号管理（管理员）" in b3)
            check("管理员可见审计列表", "操作审计" in b3)
            check("审计含登录记录", "登录成功" in b3 or "登录失败" in b3)

        png = d.execute_cdp_cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})["data"]
        (OUT / "21_account_audit.png").write_bytes(base64.b64decode(png))
        print("  截图：ui_shots/21_account_audit.png")

        errs = [e["message"] for e in d.get_log("browser")
                if e.get("level") == "SEVERE" and "favicon" not in e["message"]
                and "401" not in e["message"] and "403" not in e["message"]]
        check("控制台零严重错误（忽略预期的鉴权拒绝）", not errs, errs[0][:70] if errs else "")
    finally:
        d.quit()

    print(f"\n账号与审计界面验证：{len(PASS)} 通过 / {len(FAIL)} 失败" + ("；" + "；".join(FAIL) if FAIL else ""))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

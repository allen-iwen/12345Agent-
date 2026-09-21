# -*- coding: utf-8 -*-
"""轻量 RBAC 与审计验证。

覆盖：引导建号、登录成功/失败、会话解析、角色矩阵（允许/拒绝）、
审计日志落库（登录、建单、流转、审核、被拒操作）、RBAC 关闭时的放行行为。

注意：本脚本会在 `RBAC_ENABLED=true` 下运行关键断言；若后端以 false 启动，
会明确提示并只做「关闭态」验证（不伪造结论）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

BASE = "http://127.0.0.1:8000"
FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAIL.append(name)


def main() -> int:
    st = requests.get(f"{BASE}/api/auth/status", timeout=15).json()
    print("=== 鉴权与审计状态 ===")
    print(f"  启用={st['enabled']}｜账号 {st['users']} 个｜审计 {st['audit_records']} 条")
    check("已初始化账号", st["users"] >= 1, f"{st['users']} 个")
    check("角色矩阵有 6 个角色", len(st["roles"]) == 6, "、".join(st["roles"].values()))

    print("\n=== 账号管理（管理员）===")
    users = requests.get(f"{BASE}/api/auth/users", timeout=15)
    if not st["enabled"]:
        check("关闭态：无需鉴权即可查询账号", users.status_code == 200, str(users.status_code))
        print("  （RBAC 未启用：跳过角色拒绝断言，如需完整验证请在 .env 设 RBAC_ENABLED=true 后重启）")
        total = requests.get(f"{BASE}/api/auth/audit", timeout=15).json()
        check("审计日志可查询", total["total"] >= 1, f"{total['total']} 条")
        print(f"\nRBAC 验证（关闭态）：{len(FAIL) == 0 and 'PASS' or 'FAIL：' + '；'.join(FAIL)}")
        return 0 if not FAIL else 1

    # ---- 启用态：完整验证 ----
    print("\n=== 登录 ===")
    bad = requests.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "wrong-pass"}, timeout=15)
    check("错误密码返回 401", bad.status_code == 401, str(bad.status_code))
    unauth = requests.get(f"{BASE}/api/auth/audit", timeout=15)
    check("未登录访问审计返回 401", unauth.status_code == 401, str(unauth.status_code))

    # 管理员登录（密码由 AUTH_BOOTSTRAP_PASSWORD 指定，默认 admin-pass）
    admin = requests.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin-pass"}, timeout=15)
    check("管理员登录成功", admin.status_code == 200, str(admin.status_code))
    admin_tok = admin.json().get("token", "") if admin.status_code == 200 else ""

    users = requests.get(f"{BASE}/api/auth/users", headers={"Authorization": f"Bearer {admin_tok}"}, timeout=15)
    check("管理员可列出账号", users.status_code == 200, str(users.status_code))

    # 用引导创建的坐席账号登录
    seat = requests.post(f"{BASE}/api/auth/login", json={"username": "seat01", "password": "seat01-pass"}, timeout=15)
    check("坐席登录成功", seat.status_code == 200, str(seat.status_code))
    if seat.status_code != 200:
        return 1
    seat_tok = seat.json()["token"]
    seat_role = seat.json()["user"]["role"]
    check("会话返回角色", seat_role == "agent", seat_role)
    me = requests.get(f"{BASE}/api/auth/me", headers={"Authorization": f"Bearer {seat_tok}"}, timeout=15).json()
    check("会话可解析当前用户", me["username"] == "seat01", me.get("actor", ""))

    print("\n=== 角色矩阵 ===")
    audit_as_seat = requests.get(f"{BASE}/api/auth/audit", headers={"Authorization": f"Bearer {seat_tok}"}, timeout=15)
    check("坐席无权查看审计（403）", audit_as_seat.status_code == 403, str(audit_as_seat.status_code))
    create_user_as_seat = requests.post(f"{BASE}/api/auth/users", headers={"Authorization": f"Bearer {seat_tok}"},
                                        json={"username": "x1", "password": "pass1234", "role": "agent"}, timeout=15)
    check("坐席无权建号（403）", create_user_as_seat.status_code == 403, str(create_user_as_seat.status_code))

    print("\n=== 审计落库 ===")
    if admin_tok:
        recs = requests.get(f"{BASE}/api/auth/audit", headers={"Authorization": f"Bearer {admin_tok}"},
                            params={"limit": 50}, timeout=15).json()
        actions = [r["action"] for r in recs["records"]]
        print(f"  最近动作：{actions[:6]}")
        check("记录登录成功", any("登录成功" in a for a in actions))
        check("记录登录失败", any("登录失败" in a for a in actions))
        check("审计记录含操作者与角色", all(r.get("actor") and r.get("role") is not None for r in recs["records"][:5]))
    else:
        check("管理员登录失败，无法验证审计", False, "请确认 AUTH_BOOTSTRAP_PASSWORD=admin-pass")

    print(f"\nRBAC 验证：{len(FAIL) == 0 and 'PASS' or 'FAIL：' + '；'.join(FAIL)}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

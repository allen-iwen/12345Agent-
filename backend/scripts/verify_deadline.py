# -*- coding: utf-8 -*-
"""办理时限倒计时验证：12 条用例（含工作日/自然日/临期/超期/办结）。"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import deadline  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAIL.append(name)


def main() -> int:
    # 基准时间：2026-09-18 为周五（2026-09-20 为周日，已由系统日期确认）
    fri = datetime(2026, 9, 18, 9, 0)
    print("=== 自然日（特急/紧急）===")
    r = deadline.compute(fri, "特急", now=fri)
    check("特急到期 = 创建 + 24h", r["due_at"].startswith("2026-09-19T09:00"), r["due_at"])
    check("特急模式为自然日", r["mode"] == "自然日", r["mode"])
    check("特急状态正常", r["state"] == "正常", r["state"])
    check("特急依据为规范紧急事项条款", "24 小时" in r["basis"]["clause"], r["basis"]["clause"][:30])

    r = deadline.compute(fri, "特急", now=fri + timedelta(hours=25))
    check("特急超 25h → 超期", r["state"] == "超期", r["state"])
    check("超期附督办建议", "督办" in (r.get("supervision") or ""), (r.get("supervision") or "")[:24])

    r = deadline.compute(fri, "特急", now=fri + timedelta(hours=20))
    check("特急剩 4h → 临期", r["state"] == "临期", f"{r['state']} 剩{r['remaining_hours']}h")

    r = deadline.compute(fri, "紧急", now=fri + timedelta(hours=10))
    check("紧急剩余 14h → 正常", r["state"] == "正常", r["state"])

    print("\n=== 工作日（一般件）===")
    r = deadline.compute(fri, "一般", now=fri)
    check("一般件 5 个工作日（周五+5 → 下周五）", r["due_at"].startswith("2026-09-25T09:00"), r["due_at"])
    check("一般件模式为工作日", r["mode"] == "工作日", r["mode"])
    check("一般件时限标注为建议值", any("建议值" in n for n in r["notes"]), "；".join(r["notes"]))
    check("未配置法定节假日时显式提示", any("未配置法定节假日" in n for n in r["notes"]), "；".join(r["notes"]))
    check("一般件附承诺办理说明", "9 个月" in r["commitment_note"], r["commitment_note"][:24])

    r = deadline.compute(fri, "一般", now=fri + timedelta(days=8))
    check("一般件 8 个自然日后 → 超期", r["state"] == "超期", r["state"])

    r = deadline.compute(fri, "一般", closed=True, now=fri + timedelta(days=8))
    check("已办结案件不再计超期", r["state"] == "已办结", r["state"])

    print("\n=== 工作日推进（跳过周末 + 法定节假日）===")
    # 直接测内部函数：周五 + 5 工作日，若下周一为法定假日则顺延到再下周一
    due = deadline._add_workdays(fri, 5, frozenset({date(2026, 9, 21)}), frozenset())
    check("节假日顺延（跳过 9/21 假日 → 9/28）", due.date() == date(2026, 9, 28), due.isoformat())
    due2 = deadline._add_workdays(fri, 5, frozenset(), frozenset({date(2026, 9, 19)}))
    check("调休工作日计入（9/19 周六计为工作日 → 9/24）", due2.date() == date(2026, 9, 24), due2.isoformat())

    print(f"\n时限倒计时验证：{12 - len(FAIL)}/12 通过" + ("" if not FAIL else "；失败：" + "；".join(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

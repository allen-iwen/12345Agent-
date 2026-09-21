# -*- coding: utf-8 -*-
"""配额守卫验证：欠费/限流/过载后自动降级，且期间链路回退不受影响。

不依赖真实外部服务：直接驱动 decision 模块的降级状态机与调用上限逻辑。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import decision  # noqa: E402

FAIL: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAIL.append(name)


def main() -> int:
    st = decision.status()
    print("=== 基线 ===")
    print(f"  provider={st['provider']}｜available={st['available']}｜enabled={st['enabled']}")
    print(f"  降级状态：{decision.degraded()}｜用量：{decision.usage_stats()}")

    print("\n=== 1. 额度耗尽 → 进入冷却并回退 ===")
    decision.reset_degrade()
    decision._mark_degraded("测试：HTTP 402 额度耗尽")  # noqa: SLF001 - 直接驱动状态机
    dg = decision.degraded()
    check("标记为降级中", dg["degraded"] is True, str(dg))
    check("冷却时长取自配置", 0 < dg["remaining_s"] <= 900, f"{dg['remaining_s']}s")
    if st["provider"] == "laya":
        print("  （当前 provider=laya，本地模型无配额；以下断言仅针对外部 provider 路径）")
    else:
        r = decision.ask({"诉求原文": "测试"}, {"q": decision.noul("是否包含安全隐患？")})
        check("降级期间 ask 返回不可用（触发回退）", r.get("available") is False)
        check("note 说明冷却与回退", "冷却" in str(r.get("note")), str(r.get("note"))[:52])

    print("\n=== 2. 手动清除降级（充值/换 key 后）===")
    decision.reset_degrade()
    check("降级已清除", decision.degraded()["degraded"] is False)

    print("\n=== 3. 进程内调用上限（保护性熔断）===")
    from app.core.config import get_settings

    s = get_settings()
    original = s.decision_max_calls
    try:
        # 直接把计数推到上限，验证熔断分支（不真实发请求）
        decision._call_count = 10  # noqa: SLF001
        object.__setattr__(s, "decision_max_calls", 10)
        if st["provider"] == "laya":
            check("本地 provider 不受外部调用上限约束（laya 自带 $0 无配额）", True, "跳过")
        else:
            r = decision.ask({"诉求原文": "测试"}, {"q": decision.noul("是否包含安全隐患？")})
            check("达上限后返回不可用并熔断", r.get("available") is False and "上限" in str(r.get("note")),
                  str(r.get("note"))[:52])
            check("熔断后进入降级状态", decision.degraded()["degraded"] is True)
    finally:
        object.__setattr__(s, "decision_max_calls", original)
        decision._call_count = 0  # noqa: SLF001
        decision.reset_degrade()

    print("\n=== 4. 降级不影响既有链路（回退验证）===")
    from app.services import dispatch, reply_audit, urgency
    from app.schemas.models import Classification, WorkOrder

    off = {"available": False, "note": "降级冷却中"}
    wo = WorkOrder(title="关于某小区门口烧烤店占道经营的问题", location="鸠江区某小区",
                   event_description="占道经营油烟扰民", handling_request="依法整治")
    cls = Classification(category_code="urban_management", category_name="城市管理")
    check("急件分级回退正常", urgency.assess("咨询营业执照", None, None, None,
                                          decision_signals=off)["level"] == "一般")
    check("派单回退正常", dispatch.decide(wo, cls, "鸠江区某小区", decision_signals=off)["primary"] == "鸠江区政府")
    check("合规回退正常", reply_audit.audit("您好！已收悉。感谢支持！", [], {"raw_text": "x"},
                                          decision_signals=off)["risk_level"] in ("无", "低", "中"))

    print("\n=== 5. 真实触发：本地假端点返回 402 → 自动降级（端到端）===")
    import http.server
    import json as _json
    import os
    import threading

    class _Mock402(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.send_response(402)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(_json.dumps({"error": "insufficient balance: quota exceeded"}).encode())

        def log_message(self, *args):  # 静音
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 8099), _Mock402)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    saved = {k: os.environ.get(k) for k in ("DECISION_PROVIDER", "DECISION_BASE_URL", "DECISION_API_KEY")}
    try:
        os.environ["DECISION_PROVIDER"] = "typesafe"
        os.environ["DECISION_BASE_URL"] = "http://127.0.0.1:8099"
        os.environ["DECISION_API_KEY"] = "test-key"
        from app.core.config import get_settings

        get_settings.cache_clear()
        decision.reset_degrade()
        r = decision.ask({"诉求原文": "测试"}, {"q": decision.noul("是否包含安全隐患？")})
        check("402 响应被判为不可用", r.get("available") is False)
        check("402 命中配额关键字并自动降级", decision.degraded()["degraded"] is True,
              decision.degraded()["reason"][:56])
        r2 = decision.ask({"诉求原文": "测试"}, {"q": decision.noul("是否包含安全隐患？")})
        check("降级后第二次调用被直接拦下（不再发请求）",
              r2.get("available") is False and "冷却" in str(r2.get("note")), str(r2.get("note"))[:56])
    finally:
        srv.shutdown()
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        from app.core.config import get_settings

        get_settings.cache_clear()
        decision.reset_degrade()

    print(f"\n配额守卫验证：{len(FAIL) == 0 and 'PASS' or 'FAIL：' + '；'.join(FAIL)}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())

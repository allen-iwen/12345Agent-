import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import asr, attachments, auth, cases, flow, knowledge, policies, runs, stats, telephony, wiki

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="12345 Agent API")

# CORS 必须放在 app 创建之后、接口路由之前
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(cases.router)
app.include_router(runs.router)
app.include_router(knowledge.router)
app.include_router(asr.router)
app.include_router(policies.router)
app.include_router(telephony.router)
app.include_router(attachments.router)
app.include_router(flow.router)
app.include_router(auth.router)
app.include_router(wiki.router)
app.include_router(stats.router)


@app.on_event("startup")
def bootstrap_auth() -> None:
    """首次启动引导：创建管理员账号，随机密码只打印到控制台（不落仓库）。"""
    try:
        from app.services import auth as auth_svc

        cred = auth_svc.bootstrap()
        if cred:
            logger.warning("=" * 68)
            logger.warning("已初始化账号（仅本次打印，请立即记录并修改密码）：")
            logger.warning("  管理员  %s / %s", cred["username"], cred["password"])
            logger.warning("  另有账号 %s", cred["also_created"])
            logger.warning("=" * 68)
    except Exception:  # noqa: BLE001 - 引导失败不应阻断服务启动
        logger.warning("账号初始化失败", exc_info=True)


@app.on_event("startup")
def warm_rag() -> None:
    """后台预载政策 RAG 向量模型（bge-small-zh，首次经 modelscope 下载）。"""
    from app.services import policy_rag

    policy_rag.warm()


# ---- 生产部署：FastAPI 托管前端构建（单端口演示）----
# 必须放在全部 API 路由之后，否则静态挂载会遮蔽接口。
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="web")

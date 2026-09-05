import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import asr, cases, knowledge, policies, runs, telephony

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

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

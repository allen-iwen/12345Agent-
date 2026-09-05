"""运行轨迹 API：返回某案件所有 Agent 节点的输入/输出/耗时/状态。"""
from fastapi import APIRouter, HTTPException

from app.services import tracing

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/cases/{case_id}")
def list_case_runs(case_id: str) -> dict:
    rows = tracing.list_runs(case_id)
    return {"case_id": case_id, "runs": rows}


@router.get("/{run_id}")
def get_run(run_id: int) -> dict:
    row = tracing.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    return row
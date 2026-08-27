"""DSH 桥接层 API (v0.6 P0).

端点:
- POST /api/dsh/task   — 发送任务到 DSH / LLM fallback
- GET  /api/dsh/session/{id} — 查询会话状态
- GET  /api/dsh/health — DSH 连接健康检查
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.services.dsh.bridge import DSHClient
from backend.services.dsh.session import DSHSessionManager

router = APIRouter(prefix="/api/dsh", tags=["dsh"])

# 全局单例 (进程级, MVP 不落库)
_session_mgr = DSHSessionManager()
_dsh_client = DSHClient()


class TaskRequest(BaseModel):
    """DSH 任务请求."""
    task_type: str = Field(..., description="任务类型 (chat/summarize/classify/refactor/execute/...)")
    payload: dict[str, Any] = Field(default_factory=dict, description="任务负载")


class TaskResponse(BaseModel):
    """DSH 任务响应."""
    ok: bool
    agent: str | None = None
    session_id: str | None = None
    result: Any = None
    error: str | None = None


@router.get("/health")
def get_dsh_health() -> dict[str, Any]:
    """DSH 连接健康检查.

    返回:
    - status: "connected" | "disconnected"
    - fallback: "llm_direct" | "none"
    """
    connected = _dsh_client.health_check()
    return {
        "status": "connected" if connected else "disconnected",
        "fallback": "llm_direct" if not connected else "none",
        "endpoint": _dsh_client._endpoint,
    }


@router.post("/task", response_model=TaskResponse)
def post_dsh_task(body: TaskRequest, request: Request) -> TaskResponse:
    """发送任务到 DSH (不可达时降级 LLM 直连)."""
    session_id = _session_mgr.create_session(body.task_type, body.payload)

    try:
        result = _dsh_client.send_task(body.task_type, body.payload)
        _session_mgr.close_session(session_id)
        return TaskResponse(
            ok=True,
            agent="dsh",
            session_id=session_id,
            result=result,
        )
    except Exception as e:
        logging.getLogger("hotspot.api.dsh").warning("DSH task failed: %s", e)
        # fallback: LLM 直连
        from backend.services.dsh.task_router import DSHTaskRouter
        router = DSHTaskRouter(dsh_client=None)
        result = router.dispatch(body.task_type, body.payload)
        return TaskResponse(
            ok=result.get("ok", False),
            agent=result.get("agent", "llm_direct"),
            session_id=session_id,
            result=result.get("score") or result.get("result"),
            error=result.get("error"),
        )


@router.get("/session/{session_id}")
def get_dsh_session(session_id: str) -> dict[str, Any]:
    """查询会话状态."""
    sess = _session_mgr.get_session(session_id)
    if sess is None:
        return {"error": "session not found", "session_id": session_id}
    return sess

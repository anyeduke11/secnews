"""Agent Runner API — pi 等轻量级 CLI agent 的前端可用面 (v0.6.3)。

三层架构裁决执行层: dsh (大脑) 出决策, pi (执行 agent) 落地任务书。
端点 (前缀 /api/agents):
- GET  /api/agents/available  runner 可用性面板 (name/protocol/task_types/available)
- POST /api/agents/run        路由决策 + 子进程执行 (preferred_agent 可覆盖)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services import agent_bridge

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentRunRequest(BaseModel):
    """执行一次 agent 任务。"""

    task_type: str = Field(..., min_length=1, max_length=64, description="任务类型 (execute/refactor/quick_patch/...)")
    input: str = Field(..., min_length=1, max_length=100_000, description="任务输入 (任务书/提示词)")
    preferred_agent: str | None = Field(None, max_length=64, description="显式指定 agent (覆盖路由)")
    workspace: str | None = Field(None, max_length=500, description="工作区 (codegarden/<project>/ 相对路径)")
    payload: dict[str, Any] = Field(default_factory=dict, description="附加负载")


@router.get("/available")
def get_available_agents() -> dict[str, Any]:
    """runner 可用性面板数据。"""
    return agent_bridge.available_agents()


@router.post("/run")
def run_agent(body: AgentRunRequest) -> dict[str, Any]:
    """执行 agent 任务 (失败返回 ok=False 信封, 不抛 500)。"""
    return agent_bridge.run_agent_task(
        body.task_type,
        body.input,
        preferred_agent=body.preferred_agent,
        workspace=body.workspace,
        payload=body.payload,
    )


__all__ = ["router"]

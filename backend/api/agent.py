"""v1.7 Phase 7 — Agent API 降级 (Option A 简化版).

Phase 7 移除内部 hotspot-agent 进程 (由外部 AI Agent 通过 MCP 替代), 但保留
以下 4 个 GET 端点作为内部/调试用:

- GET    /api/agent/tasks                       拉取待处理任务 (查询式, 实际走 deprecated path)
- GET    /api/agent/tasks/{task_id}             查询单个任务详情
- GET    /api/agent/tasks/{task_id}/status      查询任务状态
- GET    /api/agent/knowledge                   知识条目列表 (查询)

**已删除的端点** (Phase 7, 由 MCP tool 替代):
- POST   /api/agent/tasks                       (MCP tool: 内部 Agent 不用)
- POST   /api/agent/tasks/{task_id}/complete    (MCP tool 同步直返, 不需要 complete)
- POST   /api/agent/knowledge                   (MCP tool: update_knowledge_item 替代)
- POST   /api/agent/start                       (没有内部 agent)
- POST   /api/agent/stop                        (没有内部 agent)
- POST   /api/agent/restart                     (没有内部 agent)
- GET    /api/agent/status                      (没有内部 agent)
- GET    /api/agent/heartbeat                   (没有内部 agent)
"""
from __future__ import annotations

import logging
import warnings
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.repository.knowledge_repo import knowledge_repo

log = logging.getLogger("hotspot.api.agent")

router = APIRouter(prefix="/api/agent", tags=["agent-deprecated"])


# ---------------------------------------------------------------------------
# 提示: 这些端点保留为 deprecated, 不再写入任务 (knowledge_tasks 表已删除)
# 仅返回 410 Gone 或空列表, 提示用户使用 MCP tool
# ---------------------------------------------------------------------------


def _warn_deprecated(endpoint: str) -> None:
    """发出 deprecation warning 日志, 引导用户使用 MCP tool。"""
    log.warning(
        "deprecated endpoint %s called; use MCP tool instead "
        "(configure AI Agent via /api/settings/mcp/config)",
        endpoint,
    )


@router.get("/tasks")
async def get_agent_tasks(
    status: str = Query("pending", description="任务状态过滤 (已弃用, 永远返回空)"),
    limit: int = Query(10, ge=1, le=50, description="最多返回条数"),
):
    """[DEPRECATED] 拉取待处理任务 — 永远返回空。

    Phase 7 后无内部 hotspot-agent, 任务调度由外部 AI Agent 通过 MCP 协议处理。
    """
    _warn_deprecated("GET /api/agent/tasks")
    return {
        "version": "1.7.6",
        "deprecated": True,
        "message": "Internal agent removed in v1.7.6. Use MCP tools instead.",
        "tasks": [],
    }


@router.get("/tasks/{task_id}/status")
async def get_agent_task_status(task_id: int):
    """[DEPRECATED] 查询任务状态 — 永远返回 410 Gone。

    knowledge_tasks 表已在 v1.7.6 migration 038 中删除。
    """
    _warn_deprecated(f"GET /api/agent/tasks/{task_id}/status")
    raise HTTPException(
        status_code=410,
        detail={
            "message": "knowledge_tasks table dropped in v1.7.6",
            "migration": "Phase 7 migration 038",
        },
    )


@router.get("/tasks/{task_id}")
async def get_agent_task(task_id: int):
    """[DEPRECATED] 查询单个任务详情 — 永远返回 410 Gone。"""
    _warn_deprecated(f"GET /api/agent/tasks/{task_id}")
    raise HTTPException(
        status_code=410,
        detail={
            "message": "knowledge_tasks table dropped in v1.7.6",
            "migration": "Phase 7 migration 038",
        },
    )


@router.get("/knowledge")
async def list_agent_knowledge(
    limit: int = Query(50, ge=1, le=200, description="最多返回条数"),
    lifecycle: Optional[str] = Query(None, description="按 lifecycle 过滤"),
):
    """[DEPRECATED] 知识条目列表 (查询式) — 实际转发到 /api/knowledge/items。

    该端点作为 alias 保留, 内部转发到 knowledge_repo 列表查询。
    """
    _warn_deprecated("GET /api/agent/knowledge")
    items = knowledge_repo.list_items(lifecycle=lifecycle, limit=limit)
    return {
        "version": "1.7.6",
        "deprecated": True,
        "items": [item.to_dict() if hasattr(item, "to_dict") else item for item in items],
    }


__all__ = ["router"]

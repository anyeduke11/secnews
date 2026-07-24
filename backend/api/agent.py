"""v1.7 Phase 5 — Agent API.

为外部 AI Agent (CLI / 独立进程) 提供双向环:
  - GET    /api/agent/tasks                       拉取待处理任务
  - POST   /api/agent/knowledge                   写回知识条目
  - POST   /api/agent/tasks/{task_id}/complete    标记任务完成
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.domain.knowledge_models import KnowledgeItem
from backend.repository.knowledge_repo import knowledge_repo
from backend.services.agent_task_service import complete_task, get_task, list_pending
from backend.services.knowledge_sync import write_item_to_md

log = logging.getLogger("hotspot.api.agent")

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class AgentKnowledgePayload(BaseModel):
    """Agent 写回知识条目的载荷."""

    item_id: str = Field(..., description="条目 ID (e.g. cubox-abc123)")
    title: str = Field("", description="标题")
    content: str = Field("", description="Markdown 正文")
    lifecycle: str = Field("signal", description="SAG 生命周期: signal/generate/refine/compose")
    tags: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    domain: str = Field("", description="领域: security/ai/finance/startup/github")
    topic: str = Field("", description="主题")
    difficulty: str = Field("intermediate", description="难度: beginner/intermediate/advanced")
    source: str = Field("agent", description="来源标识")


class AgentCompletePayload(BaseModel):
    """Agent 完成任务回执."""

    status: str = Field("done", description="done | failed")
    result: dict = Field(default_factory=dict, description="执行结果")
    error: str = Field("", description="错误信息 (status=failed 时)")


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/tasks")
async def get_agent_tasks(
    status: str = Query("pending", description="任务状态过滤"),
    limit: int = Query(10, ge=1, le=50, description="最多返回条数"),
):
    """Agent 拉取待处理任务. 按 created_at 升序 (FIFO)."""
    if status == "pending":
        tasks = list_pending(limit=limit)
    else:
        # 其他状态: 直接查 DB
        from backend.repository.knowledge_repo import knowledge_repo
        all_tasks = knowledge_repo.list_tasks(status=status)
        tasks = [
            {
                "task_id": t.id,
                "task_type": t.task_type,
                "status": t.status,
                "target_type": (t.params or {}).get("target_type", ""),
                "target_id": (t.params or {}).get("target_id", ""),
                "priority": (t.params or {}).get("priority", 1),
                "created_at": t.created_at,
                "params": t.params or {},
            }
            for t in all_tasks[:limit]
        ]
    return {"version": "1.7.0", "tasks": tasks}


@router.post("/knowledge")
async def write_agent_knowledge(payload: AgentKnowledgePayload):
    """Agent 写回知识条目: 更新 DB + 写 .md 文件.

    双向环:
      前端/Agent 修改 → POST /api/agent/knowledge → 同步到 knowledge/items/*.md
      .md 文件变更 → knowledge_watcher → 同步到 DB (闭环)
    """
    # 读取已有条目 (如果存在)
    item = knowledge_repo.get_item(payload.item_id)
    if item is None:
        # 新建条目
        from backend.domain.knowledge_models import now_iso
        item = KnowledgeItem(
            id=payload.item_id,
            title=payload.title,
            source=payload.source,
            source_url="",
            domain=payload.domain,
            topic=payload.topic,
            type="article",
            difficulty=payload.difficulty,
            tags=payload.tags,
            concepts=payload.concepts,
            lifecycle=payload.lifecycle,
            tech_stack=payload.tech_stack,
            ingested_at=now_iso(),
            updated_at=now_iso(),
        )
    else:
        # 更新已有条目
        item.title = payload.title or item.title
        item.lifecycle = payload.lifecycle
        item.tags = payload.tags
        item.concepts = payload.concepts
        item.tech_stack = payload.tech_stack
        if payload.domain:
            item.domain = payload.domain
        if payload.topic:
            item.topic = payload.topic
        if payload.difficulty:
            item.difficulty = payload.difficulty

    # 写 DB + 写 .md 文件
    knowledge_repo.upsert_item(item)
    try:
        # write_item_to_md 支持可选 content 参数: 显式传入时覆盖正文
        write_item_to_md(item.to_dict(), content=payload.content)
    except Exception as e:
        log.warning("write_item_to_md 失败 (但 DB 已更新): %s", e)

    # 失效 KV 缓存 (双向环闭合)
    try:
        from backend.services.kv_cache_service import kv_cache
        kv_cache.invalidate_item(payload.item_id)
    except Exception as e:
        log.debug("kv_cache invalidate 跳过: %s", e)

    log.info("agent wrote knowledge: %s lifecycle=%s", payload.item_id, payload.lifecycle)
    return {
        "success": True,
        "item_id": payload.item_id,
        "lifecycle": payload.lifecycle,
    }


@router.post("/tasks/{task_id}/complete")
async def complete_agent_task(
    task_id: int,
    payload: AgentCompletePayload,
):
    """Agent 标记任务完成: 更新 DB + 移动任务文件.

    Args:
        task_id: 任务 ID (来自 GET /api/agent/tasks)
        payload.status: "done" | "failed"
        payload.result: 执行结果 (写入 params.result)
        payload.error: 失败原因
    """
    if payload.status not in ("done", "failed", "processing"):
        raise HTTPException(
            status_code=400,
            detail=f"invalid status: {payload.status} (must be done/failed/processing)",
        )

    # 任务存在性检查
    existing = get_task(task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")

    result = complete_task(
        task_id=task_id,
        status=payload.status,
        result=payload.result if payload.result else None,
        error=payload.error,
    )
    return result


@router.get("/tasks/{task_id}")
async def get_agent_task(task_id: int):
    """查询单个任务详情."""
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    return task

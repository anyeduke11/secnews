"""v0.6 Phase 5 commit 3 — MCP tool 扩展 (5 个新 tool).

设计
----
- 复用现有 FastAPI 端点 (/api/kl/pipeline/*, /api/dsh/*) 作为底层实现,
  在 MCP 入口处提供更紧致、agent 友好的 input/output schema。
- 通过 fastapi-mcp 注册到 MCP server (operation_id 见 mcp_config.py)。
- 由 feature_gates 'mcp' 控制注册 (与已有 mcp_* 路由一致)。

5 个 tool
---------
- kl_enqueue    POST /api/mcp/kl/enqueue       推进单个 item 到下一阶段
- kl_status     GET  /api/mcp/kl/status        漏斗 + 队列 + 错误 + 计数
- kl_retry      POST /api/mcp/kl/retry         重试错误任务
- dsh_analyze   POST /api/mcp/dsh/analyze      DSH classify 任务 (含 LLM fallback)
- dsh_session   GET  /api/mcp/dsh/session/{id} 查询 DSH 会话状态
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("hotspot.api.mcp_phase5")

# 3 个 kl_* tool: /api/mcp/kl/*  (与既有 /api/kl/pipeline/* 区分,
# 此处专供 MCP agent 调用, input 更紧致, output 精简)
kl_router = APIRouter(prefix="/api/mcp/kl", tags=["mcp-kl-tools"])

# 2 个 dsh_* tool: /api/mcp/dsh/*
dsh_router = APIRouter(prefix="/api/mcp/dsh", tags=["mcp-dsh-tools"])


# ===========================================================================
# KL 工具 — Input/Output 模型
# ===========================================================================
class KlEnqueueInput(BaseModel):
    """kl_enqueue — 推进单个 item 到下一阶段 (由 kl_state_machine 校验合法性)。

    等价于 POST /api/kl/pipeline/advance, input 收紧为必填 item_id。
    """
    item_id: str = Field(..., min_length=1, description="knowledge_item id (wiki file stem)")


class KlRetryInput(BaseModel):
    """kl_retry — 重试 error 任务 (可选按 wiki_id 过滤)。

    等价于 POST /api/kl/pipeline/retry, input 可选 wiki_id。
    """
    wiki_id: str | None = Field(None, description="可选, 仅重试指定 wiki_id 的错误任务")


# ===========================================================================
# DSH 工具 — Input/Output 模型
# ===========================================================================
class DshAnalyzeInput(BaseModel):
    """dsh_analyze — 调用 DSH classify 任务 (fallback LLM)。

    等价于 POST /api/dsh/task (task_type=classify), 简化 agent 调用。
    """
    content: str = Field(..., min_length=1, description="待分类文本 (URL / 标题 / 段落)")
    hint: str | None = Field(None, description="可选上下文 (用于引导分类标签)")


# ===========================================================================
# KL 端点
# ===========================================================================
@kl_router.post("/enqueue")
async def kl_enqueue(req: KlEnqueueInput) -> dict[str, Any]:
    """推进单个 item 到下一阶段 (kl_state_machine 校验)."""
    try:
        from backend.kl_pipeline.runtime import get_production_pipeline
        pipeline = get_production_pipeline()
    except Exception as e:
        logger.warning("kl_enqueue: pipeline unavailable: %s", e)
        raise HTTPException(
            status_code=503,
            detail={"message": f"KL pipeline unavailable: {e}"},
        )

    try:
        new_stage = pipeline.advance(req.item_id)
        return {"item_id": req.item_id, "new_stage": new_stage}
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"message": str(e)})


@kl_router.get("/status")
async def kl_status() -> dict[str, Any]:
    """返回漏斗 + 队列 + 错误 + 计数 (与 /api/kl/pipeline/stats 等价)."""
    try:
        from backend.kl_pipeline.obs.funnel import funnel_stats
        from backend.kl_pipeline.obs.ledger import TokenLedger
        from backend.kl_pipeline.runtime import (
            get_production_pipeline,
            get_production_wiki_fs,
        )
        from backend.repository.db import get_connection
        from backend.wiki_fs.liveness import liveness_counts
        pipeline = get_production_pipeline()
        wiki_fs = get_production_wiki_fs()
        return {
            "funnel": funnel_stats(wiki_fs),
            "queue": pipeline.queue.stats(),
            "errors": pipeline.queue.errors(limit=10),
            "alive": liveness_counts(wiki_fs),
            "ledger": TokenLedger(get_connection()).summary(),
        }
    except Exception as e:
        logger.warning("kl_status: stats failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail={"message": f"KL stats unavailable: {e}"},
        )


@kl_router.post("/retry")
async def kl_retry(req: KlRetryInput) -> dict[str, Any]:
    """重试错误任务 (可选按 wiki_id 过滤)."""
    try:
        from backend.kl_pipeline.runtime import get_production_pipeline
        pipeline = get_production_pipeline()
        count = pipeline.retry_errors(req.wiki_id)
        return {"retried": count, "wiki_id": req.wiki_id}
    except Exception as e:
        logger.warning("kl_retry: retry failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail={"message": f"KL retry failed: {e}"},
        )


# ===========================================================================
# DSH 端点
# ===========================================================================
@dsh_router.post("/analyze")
async def dsh_analyze(req: DshAnalyzeInput) -> dict[str, Any]:
    """DSH classify 任务 (含 LLM fallback).

    实现: 调用 /api/dsh/task 内部逻辑, task_type='classify'。
    """
    # 直接调用 DSH 模块而非 HTTP 自调, 避免 listen 自身
    try:
        from backend.services.dsh.bridge import DSHClient
        from backend.services.dsh.session import DSHSessionManager
        from backend.services.dsh.task_router import DSHTaskRouter

        client = DSHClient()
        sess_mgr = DSHSessionManager()
        payload = {"content": req.content, "hint": req.hint or ""}

        session_id = sess_mgr.create_session("classify", payload)
        try:
            result = client.send_task("classify", payload)
            sess_mgr.close_session(session_id)
            return {
                "ok": True,
                "agent": "dsh",
                "session_id": session_id,
                "result": result,
            }
        except Exception as e:
            logger.warning("dsh_analyze: DSH failed, fallback LLM: %s", e)
            router = DSHTaskRouter(dsh_client=None)
            result = router.dispatch("classify", payload)
            return {
                "ok": result.get("ok", False),
                "agent": result.get("agent", "llm_direct"),
                "session_id": session_id,
                "result": result.get("score") or result.get("result"),
                "error": result.get("error"),
            }
    except Exception as e:
        logger.warning("dsh_analyze: unexpected error: %s", e)
        raise HTTPException(
            status_code=500,
            detail={"message": f"dsh_analyze failed: {e}"},
        )


@dsh_router.get("/session/{session_id}")
async def dsh_session(session_id: str) -> dict[str, Any]:
    """查询 DSH 会话状态."""
    try:
        from backend.services.dsh.session import DSHSessionManager
        sess_mgr = DSHSessionManager()
        sess = sess_mgr.get_session(session_id)
        if sess is None:
            return {"error": "session not found", "session_id": session_id}
        return sess
    except Exception as e:
        logger.warning("dsh_session: lookup failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail={"message": f"dsh_session lookup failed: {e}"},
        )


__all__ = ["dsh_router", "kl_router"]

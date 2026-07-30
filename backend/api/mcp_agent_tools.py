"""MCP Agent 侧写 tool（副作用模式，原 Phase 8）

提供 4 个独立写 tool：
- score_item: 写入 ai_scores 表
- enrich_concept: 写入 concepts/{name}.md
- link_items: 写入 knowledge_links 表
- trigger_codegarden_drift: 评估 project tech_stack（当前 stub）
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.repository.db import get_connection

logger = logging.getLogger("hotspot.api.mcp_agent_tools")

# URL 前缀保持 /api/mcp/phase8 不变: 外部 MCP agent (claude-desktop/cursor) 的 HTTP 契约
router = APIRouter(prefix="/api/mcp/phase8", tags=["mcp-agent-tools"])

# 可被测试覆盖的模块级常量
CONCEPT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "knowledge",
    "concepts",
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ScoreItemRequest(BaseModel):
    hotspot_id: str = Field(..., min_length=1)
    score: float = Field(..., ge=0, le=10)
    reason: Optional[str] = None
    scorer: str = Field(..., pattern=r"^(agent:claude-desktop|agent:cursor|rule)$")


class EnrichConceptRequest(BaseModel):
    concept_name: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    source: Optional[str] = None


class LinkItemsRequest(BaseModel):
    from_id: str = Field(..., min_length=1)
    to_id: str = Field(..., min_length=1)
    link_type: str = Field(..., pattern=r"^(similar|prerequisite|extension|contradiction|source)$")
    confidence: Optional[float] = Field(default=0.5, ge=0, le=1)


class TriggerDriftRequest(BaseModel):
    project_id: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# score_item — 写入 ai_scores 表
# ---------------------------------------------------------------------------
@router.post("/score-item")
async def score_item(req: ScoreItemRequest):
    """写入 ai_scores 表（MCP tool: score_item）。"""
    def _run() -> dict:
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO ai_scores (hotspot_id, score, reason, scorer, scored_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                req.hotspot_id,
                req.score,
                req.reason,
                req.scorer,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return {"status": "ok", "score_id": cur.lastrowid}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logger.error("score_item failed", extra={"trace_id": "", "error": str(e)})
        raise HTTPException(status_code=500, detail={"message": str(e)})


# ---------------------------------------------------------------------------
# enrich_concept — 写入 concepts/{name}.md
# ---------------------------------------------------------------------------
@router.post("/enrich-concept")
async def enrich_concept(req: EnrichConceptRequest):
    """写入 concepts/{name}.md（MCP tool: enrich_concept）。"""
    def _run() -> dict:
        os.makedirs(CONCEPT_DIR, exist_ok=True)
        filepath = os.path.join(CONCEPT_DIR, f"{req.concept_name}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(
                f"---\n"
                f"title: {req.concept_name}\n"
                f"source: {req.source or 'agent'}\n"
                f"created_at: {datetime.now(timezone.utc).isoformat()}\n"
                f"---\n\n"
                f"{req.content}"
            )
        return {"status": "ok", "file": f"concepts/{req.concept_name}.md"}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logger.error("enrich_concept failed", extra={"trace_id": "", "error": str(e)})
        raise HTTPException(status_code=500, detail={"message": str(e)})


# ---------------------------------------------------------------------------
# link_items — 写入 knowledge_links 表
# ---------------------------------------------------------------------------
@router.post("/link-items")
async def link_items(req: LinkItemsRequest):
    """写入 knowledge_links 表（MCP tool: link_items）。"""
    def _run() -> dict:
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO knowledge_links "
            "(from_item_id, to_item_id, link_type, confidence, created_by) "
            "VALUES (?, ?, ?, ?, 'agent')",
            (req.from_id, req.to_id, req.link_type, req.confidence),
        )
        return {"status": "ok", "link_id": cur.lastrowid}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        logger.error("link_items failed", extra={"trace_id": "", "error": str(e)})
        raise HTTPException(status_code=500, detail={"message": str(e)})


# ---------------------------------------------------------------------------
# trigger_codegarden_drift — 评估 project tech_stack（Phase 13 完善）
# ---------------------------------------------------------------------------
@router.post("/trigger-codegarden-drift")
async def trigger_codegarden_drift(req: TriggerDriftRequest):
    """评估 project tech_stack（MCP tool: trigger_codegarden_drift）。

    Phase 13 实现完整的 tech_stack 评估；当前返回 stub（drift_score=0.0）。
    """
    return {"status": "ok", "drift_score": 0.0}


__all__ = ["router"]
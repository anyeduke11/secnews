"""v1 Knowledge API — 复用记录 + 知识采用 (C12 R16).

拆自 ``backend/api/knowledge_api.py`` (R3 行数收缩): handler 逻辑逐字搬移,
prefix 由本 router 自带 (惰性展开惯例), URL/method 逐字不变。

- ``GET  /api/v1/knowledge/{id}/reuse``     §9.4 复用记录派生 (by_decision/by_outcome)
- ``POST /api/v1/knowledge/{id}/adopt``     记录一次采用 (decision + condition_diff)
- ``GET  /api/v1/knowledge/{id}/adoptions`` 列出所有 adoptions
- ``POST /api/v1/knowledge/{id}/outcome``   记录采用结果 (success|partial|failure)
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from backend.services.knowledge_service import (
    KnowledgeConflictError,
    KnowledgeNotFoundError,
    KnowledgeService,
    KnowledgeValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/knowledge", tags=["v1-knowledge"])


# ---------------------------------------------------------------------------
# C12 R16 — 知识采用 (adopt / outcome) 请求模型
# ---------------------------------------------------------------------------
class AdoptKnowledgeRequest(BaseModel):
    """POST /api/v1/knowledge/{id}/adopt — 记录一次采用 (decision + condition_diff)."""

    case_id: str = Field(min_length=1, max_length=26)
    decision: str = Field(pattern="^(adopted|skipped|rejected)$")
    condition_diff: list[dict[str, Any]] = Field(default_factory=list)
    decided_by: str = Field(min_length=1, max_length=200)
    adopted_by: str | None = None


class OutcomeKnowledgeRequest(BaseModel):
    """POST /api/v1/knowledge/{id}/outcome — 记录采用结果."""

    case_id: str = Field(min_length=1, max_length=26)
    outcome: str = Field(pattern="^(success|partial|failure)$")
    outcome_note: str | None = Field(default=None, max_length=2000)


def _reuse(knowledge_id: str) -> dict[str, Any]:
    """C12 R16.5: 复用记录只数 adoptions — {total, by_decision, by_outcome, recent_30d}.

    旧 {by_judgment, by_action} 字段 (derived_from 误统计) 已弃用.
    """
    svc = KnowledgeService()
    try:
        receipt = svc.get_reuse_receipt(knowledge_id)
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    return {"version": API_VERSION, "knowledge_id": knowledge_id, "receipt": receipt}


def _adopt(knowledge_id: str, req: AdoptKnowledgeRequest) -> dict[str, Any]:
    svc = KnowledgeService()
    try:
        adoption = svc.record_adoption(
            knowledge_id=knowledge_id,
            case_id=req.case_id,
            condition_diff=req.condition_diff,
            decision=req.decision,
            decided_by=req.decided_by,
            adopted_by=req.adopted_by,
        )
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except KnowledgeValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    except KnowledgeConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    return {"version": API_VERSION, "adoption": adoption}


def _list_adoptions(knowledge_id: str) -> dict[str, Any]:
    """GET /api/v1/knowledge/{id}/adoptions — 列出该 knowledge 的所有 adoptions."""
    svc = KnowledgeService()
    # 验证存在性
    try:
        svc.get(knowledge_id)
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    items = svc.list_adoptions(knowledge_id)
    return {"version": API_VERSION, "knowledge_id": knowledge_id, "items": items, "total": len(items)}


def _outcome(knowledge_id: str, req: OutcomeKnowledgeRequest) -> dict[str, Any]:
    svc = KnowledgeService()
    try:
        outcome = svc.record_outcome(
            knowledge_id=knowledge_id,
            case_id=req.case_id,
            outcome=req.outcome,
            outcome_note=req.outcome_note,
        )
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except KnowledgeValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    return {"version": API_VERSION, "outcome": outcome}


@router.get("/{knowledge_id}/reuse", response_model=None)
async def get_knowledge_reuse(knowledge_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_reuse, knowledge_id)


@router.post("/{knowledge_id}/adopt", response_model=None)
async def adopt_knowledge(
    knowledge_id: str, req: AdoptKnowledgeRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_adopt, knowledge_id, req)


@router.get("/{knowledge_id}/adoptions", response_model=None)
async def list_knowledge_adoptions(knowledge_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_list_adoptions, knowledge_id)


@router.post("/{knowledge_id}/outcome", response_model=None)
async def outcome_knowledge(
    knowledge_id: str, req: OutcomeKnowledgeRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_outcome, knowledge_id, req)

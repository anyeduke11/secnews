"""v1.0 T08 Case API — 写路径 (创建 / 关闭, contracts §4 + §0.4).

拆自 ``backend/api/case_api.py`` (R3 行数收缩): handler 逻辑逐字搬移,
prefix 由本 router 自带 (惰性展开惯例), URL/method 逐字不变。

- ``POST /api/v1/cases``            创建 — body: title/question/goal/scope/priority/...
- ``POST /api/v1/cases/{id}/close`` 关闭 — body 必含 expected_revision (CAS)

close 的 CAS 语义 (expected_revision 不匹配 → 409 E_CONFLICT) 原样保留。
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from backend.api.v1_case_common import _case_to_dict
from backend.logging_config import logger
from backend.services.case_service import (
    CaseConflictError,
    CaseNotFoundError,
    CaseService,
    CaseValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/cases", tags=["v1-cases"])


# ---------------------------------------------------------------------------
# Request 模型
# ---------------------------------------------------------------------------
class CreateCaseRequest(BaseModel):
    """POST /api/v1/cases body — 必填 title + question, 其它可选."""

    title: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=500)
    goal: str | None = None
    scope: str | None = None
    priority: str = Field(default="p2", pattern="^(p0|p1|p2|p3)$")
    due_at: str | None = None
    subject_id: str | None = None
    owner_role: str = Field(default="user", pattern="^(user|system|shared)$")
    tags: list[str] = Field(default_factory=list)
    related_subject_ids: list[str] = Field(default_factory=list)
    related_signal_ids: list[str] = Field(default_factory=list)
    related_case_ids: list[str] = Field(default_factory=list)
    source: str = Field(default="manual", description="提交方标识 (manual|agent|system)")


class CloseCaseRequest(BaseModel):
    """POST /api/v1/cases/{id}/close body."""

    expected_revision: int = Field(ge=1)


# ---------------------------------------------------------------------------
# 同步 helper (放线程池)
# ---------------------------------------------------------------------------
def _create(req: CreateCaseRequest) -> dict[str, Any]:
    svc = CaseService()
    try:
        case = svc.create_case(
            title=req.title,
            question=req.question,
            goal=req.goal,
            scope=req.scope,
            priority=req.priority,
            due_at=req.due_at,
            subject_id=req.subject_id,
            owner_role=req.owner_role,
            tags=req.tags,
            related_subject_ids=req.related_subject_ids,
            related_signal_ids=req.related_signal_ids,
            related_case_ids=req.related_case_ids,
            source=req.source,
        )
    except CaseValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    except CaseConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "E_CONFLICT",
                "message": str(e),
                "current_revision": e.current_revision,
                "current_status": e.current_status,
            },
        )
    return {"version": API_VERSION, "item": _case_to_dict(case)}


def _close(case_id: str, req: CloseCaseRequest) -> dict[str, Any]:
    svc = CaseService()
    try:
        case = svc.close_case(case_id, expected_revision=req.expected_revision)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "E_NOT_FOUND", "message": str(e)},
        )
    except CaseConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "E_CONFLICT",
                "message": str(e),
                "current_revision": e.current_revision,
                "current_status": e.current_status,
            },
        )
    return {"version": API_VERSION, "item": _case_to_dict(case)}


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@router.post("", status_code=201)
async def create_case_endpoint(req: CreateCaseRequest = Body(...)):
    """创建 Case — 走 V1EvidenceService.create_intent + commit_intent."""
    try:
        return await asyncio.to_thread(_create, req)
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover — 兜底
        logger.exception(f"create_case unhandled: {e}")
        raise HTTPException(
            status_code=500,
            detail={"code": "E_INTERNAL", "message": str(e)},
        )


@router.post("/{case_id}/close", status_code=200)
async def close_case_endpoint(case_id: str, req: CloseCaseRequest = Body(...)):
    """关闭 Case — 校验无 active run, 落 closed_at."""
    return await asyncio.to_thread(_close, case_id, req)

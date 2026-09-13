"""v1.0 T08 Case API — CAS 字段更新 (PATCH, contracts §4).

拆自 ``backend/api/case_api.py`` (R3 行数收缩): handler 逻辑逐字搬移,
prefix 由本 router 自带 (惰性展开惯例), URL/method 逐字不变。

- ``PATCH /api/v1/cases/{id}`` — CAS 更新, body 必含 expected_revision
  (不匹配 → 409 E_CONFLICT, 附 current_revision/current_status)。
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from backend.api.v1_case_common import _case_to_dict
from backend.services.case_service import (
    CaseConflictError,
    CaseNotFoundError,
    CaseService,
    CaseValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/cases", tags=["v1-cases"])


class UpdateCaseRequest(BaseModel):
    """PATCH /api/v1/cases/{id} body — 必填 expected_revision (CAS)."""

    expected_revision: int = Field(ge=1)
    status: str | None = Field(default=None, pattern="^(open|in_progress|blocked|closed|archived)$")
    title: str | None = Field(default=None, max_length=120)
    question: str | None = Field(default=None, max_length=500)
    goal: str | None = None
    scope: str | None = None
    priority: str | None = Field(default=None, pattern="^(p0|p1|p2|p3)$")
    due_at: str | None = None
    tags: list[str] | None = None
    related_subject_ids: list[str] | None = None
    related_signal_ids: list[str] | None = None
    related_case_ids: list[str] | None = None
    reason: str | None = None


def _update(case_id: str, req: UpdateCaseRequest) -> dict[str, Any]:
    svc = CaseService()
    try:
        case = svc.update_case(
            case_id,
            expected_revision=req.expected_revision,
            status=req.status,
            title=req.title,
            question=req.question,
            goal=req.goal,
            scope=req.scope,
            priority=req.priority,
            due_at=req.due_at,
            tags=req.tags,
            related_subject_ids=req.related_subject_ids,
            related_signal_ids=req.related_signal_ids,
            related_case_ids=req.related_case_ids,
            reason=req.reason,
        )
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
    except CaseValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "E_VALIDATION", "message": str(e)},
        )
    return {"version": API_VERSION, "item": _case_to_dict(case)}


@router.patch("/{case_id}")
async def update_case_endpoint(case_id: str, req: UpdateCaseRequest = Body(...)):
    """CAS 更新 — body 必含 expected_revision."""
    return await asyncio.to_thread(_update, case_id, req)

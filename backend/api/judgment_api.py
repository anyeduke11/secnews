"""v1.0 T11 Judgment API (contracts §5 + §0.4).

路由清单 (前缀 /api/v1/judgments)
--------
- ``POST /api/v1/judgments/generate``  **已退役 (v0.8.6 P1-1 收编, 410)** —
  dsh 绕审批直落 draft 违反"人主律"; 起草唯一入口 =
  ``POST /api/proposals/draft-judgment`` (审批收件箱, DEV-0264)
- ``GET  /api/v1/judgments``            列表 (query: case_id 必填 + status/claim_type/limit/offset)
- ``GET  /api/v1/judgments/{id}``       详情
- ``POST /api/v1/judgments/{id}/publish``  publish draft → published (CAS expected_revision)

错误
----
- ``E_VALIDATION`` (400) — 字段校验 / payload 错误 / dsh 响应解析失败
- ``E_NOT_FOUND``  (404) — id 不存在
- ``E_CONFLICT``   (409) — revision 不匹配 (CAS) / 同 case 同一 claim_type 已 published
- 响应一律包含 allowed_actions + revision + reason (contracts §0.3)
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.judgment_service import (
    JudgmentConflictError,
    JudgmentNotFoundError,
    JudgmentService,
    JudgmentValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/judgments", tags=["v1-judgments"])


# ---------------------------------------------------------------------------
# Request / Response 模型
# ---------------------------------------------------------------------------
class PublishJudgmentRequest(BaseModel):
    """POST /api/v1/judgments/{id}/publish — body 必须含 expected_revision."""

    expected_revision: int = Field(ge=1)


_RETIRED_GENERATE_DETAIL = {
    "code": "E_RETIRED",
    "message": (
        "POST /judgments/generate retired in v0.8.6 P1-1 (审批收编): "
        "dsh 直落 draft 绕过人审与'人主律'冲突; "
        "起草请走 POST /api/proposals/draft-judgment, 产物经 /action 审批收件箱"
    ),
}


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------
def _judgment_to_dict(j: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": j["id"],
        "case_id": j["case_id"],
        "subject_id": j.get("subject_id"),
        "claim_type": j["claim_type"],
        "claim": j["claim"],
        "conditions": j.get("conditions", ""),
        "confidence": j["confidence"],
        "evidence_refs": j.get("evidence_refs", []),
        "counter_evidence_refs": j.get("counter_evidence_refs", []),
        "unknowns": j.get("unknowns", []),
        "status": j["status"],
        "content_hash": j.get("content_hash"),
        "wiki_path": j.get("wiki_path"),
        "revision": j["revision"],
        "published_at": j.get("published_at"),
        "allowed_actions": j.get("allowed_actions", []),
        "reason": j.get("reason"),
        "created_at": j["created_at"],
        "updated_at": j["updated_at"],
    }


def _list_response(items: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {
        "version": API_VERSION,
        "items": [_judgment_to_dict(j) for j in items],
        "total": total if total is not None else len(items),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/generate", response_model=None)
async def generate_judgment() -> dict[str, Any]:
    """v0.8.6 P1-1 收编: 已退役 (410) — 起草走 /api/proposals/draft-judgment。"""
    raise HTTPException(status_code=410, detail=dict(_RETIRED_GENERATE_DETAIL))


def _list(
    case_id: str,
    status: str | None,
    claim_type: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    svc = JudgmentService()
    result = svc.list_by_case(
        case_id, status=status, claim_type=claim_type, limit=limit, offset=offset,
    )
    return _list_response(result["items"], total=result["total"])


def _get(judgment_id: str) -> dict[str, Any]:
    svc = JudgmentService()
    try:
        j = svc.get(judgment_id)
    except JudgmentNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    return {"version": API_VERSION, "item": _judgment_to_dict(j)}


def _publish(judgment_id: str, req: PublishJudgmentRequest) -> dict[str, Any]:
    svc = JudgmentService()
    try:
        j = svc.publish(judgment_id, expected_revision=req.expected_revision)
    except JudgmentNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except JudgmentConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    except JudgmentValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    return {"version": API_VERSION, "item": _judgment_to_dict(j)}


# ---------------------------------------------------------------------------
# 路由注册 (走 asyncio.to_thread 同步 DB)
# ---------------------------------------------------------------------------


@router.get("", response_model=None)
async def list_judgments(
    case_id: str = Query(..., min_length=1, max_length=26),
    status: str | None = Query(None, pattern="^(draft|published|superseded|retracted)$"),
    claim_type: str | None = Query(
        None, pattern="^(finding|assessment|recommendation|warning|hypothesis)$"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return await asyncio.to_thread(_list, case_id, status, claim_type, limit, offset)


@router.get("/{judgment_id}", response_model=None)
async def get_judgment(judgment_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_get, judgment_id)


@router.post("/{judgment_id}/publish", response_model=None)
async def publish_judgment(
    judgment_id: str, req: PublishJudgmentRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_publish, judgment_id, req)

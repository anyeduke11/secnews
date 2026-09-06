"""v1.0 T11 Judgment API (contracts §5 + §0.4).

路由清单 (前缀 /api/v1/judgments)
--------
- ``POST /api/v1/judgments/generate``  dsh 调 cve-impact-brief, 落 draft
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

from backend.logging_config import logger
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
class GenerateJudgmentRequest(BaseModel):
    """POST /api/v1/judgments/generate — dsh 调 cve-impact-brief 落 draft."""

    case_id: str = Field(min_length=1, max_length=26)
    cve_id: str = Field(min_length=1, max_length=64, description="例 CVE-2026-31337")
    subject_name: str = Field(min_length=1, max_length=200)
    evidence_materials: list[dict[str, Any]] = Field(
        default_factory=list,
        description="[{id, title, content_hash, summary?}, ...]",
    )
    submitted_by: str = Field(default="user")


class PublishJudgmentRequest(BaseModel):
    """POST /api/v1/judgments/{id}/publish — body 必须含 expected_revision."""

    expected_revision: int = Field(ge=1)


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
def _generate(req: GenerateJudgmentRequest) -> dict[str, Any]:
    svc = JudgmentService()
    try:
        result = svc.create_with_dsh(
            case_id=req.case_id,
            cve_id=req.cve_id,
            subject_name=req.subject_name,
            evidence_materials=req.evidence_materials,
            submitted_by=req.submitted_by,
        )
    except JudgmentValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    except JudgmentConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    return {
        "version": API_VERSION,
        "item": _judgment_to_dict(result["judgment"]),
        "idempotent_replay": result["idempotent_replay"],
    }


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
@router.post("/generate", response_model=None)
async def generate_judgment(req: GenerateJudgmentRequest) -> dict[str, Any]:
    return await asyncio.to_thread(_generate, req)


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

"""v1.0 T12 Artifact API (contracts §8 + §0.4) — 创建 + 验证 + 验收 + 拒绝 + 列表 + 详情."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.artifact_service import (
    ArtifactConflictError,
    ArtifactNotFoundError,
    ArtifactService,
    ArtifactValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/artifacts", tags=["v1-artifacts"])


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------
class CreateArtifactRequest(BaseModel):
    """POST /api/v1/artifacts — 创建 (走 run_id; 默认 status=pending)."""

    run_id: str = Field(min_length=1, max_length=40)
    kind: str = Field(pattern="^(report|file|data|chart|code_patch|message)$")
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, description="文本内容, 服务层算 hash")
    format: str = Field(default="md", pattern="^(md|json|csv|png|pdf|txt|html|xml)$")
    content_ref: str | None = None


class VerifyArtifactRequest(BaseModel):
    """POST /api/v1/artifacts/{id}/verify — 验证 (pass/fail/warn).

    v0.8.5 D2 (R09 API 层): expected_revision 可选透传 — 客户端聚合读到的
    revision 与服务端当前不符时 409 E_CONFLICT (契约 §0.6 CAS)。
    """

    verified_by: str = Field(min_length=1, max_length=200)
    verified_result: str = Field(default="pass", pattern="^(pass|fail|warn)$")
    expected_revision: int | None = Field(default=None, ge=1)


class AcceptArtifactRequest(BaseModel):
    """POST /api/v1/artifacts/{id}/accept — 业务验收 (verified → accepted)."""

    accepted_by: str = Field(min_length=1, max_length=200)
    accepted_note: str | None = None
    expected_revision: int | None = Field(default=None, ge=1)


class RejectArtifactRequest(BaseModel):
    """POST /api/v1/artifacts/{id}/reject — 拒绝 (pending/verified → rejected)."""

    rejected_by: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    expected_revision: int | None = Field(default=None, ge=1)


def _artifact_to_dict(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": a["id"],
        "run_id": a["run_id"],
        "kind": a["kind"],
        "title": a["title"],
        "content_ref": a.get("content_ref"),
        "content_hash": a["content_hash"],
        "format": a["format"],
        "size_bytes": a["size_bytes"],
        "verified_by": a.get("verified_by"),
        "verified_at": a.get("verified_at"),
        "verified_result": a.get("verified_result"),
        "accepted_by": a.get("accepted_by"),
        "accepted_at": a.get("accepted_at"),
        "accepted_note": a.get("accepted_note"),
        "status": a["status"],
        "revision": a["revision"],
        "allowed_actions": a.get("allowed_actions", []),
        "reason": a.get("reason"),
        "created_at": a["created_at"],
        "updated_at": a["updated_at"],
    }


def _list_response(items: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {
        "version": API_VERSION,
        "items": [_artifact_to_dict(a) for a in items],
        "total": total if total is not None else len(items),
    }


def _create(req: CreateArtifactRequest) -> dict[str, Any]:
    svc = ArtifactService()
    try:
        a = svc.create(
            run_id=req.run_id, kind=req.kind, title=req.title,
            content=req.content, format=req.format, content_ref=req.content_ref,
        )
    except ArtifactValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    return {"version": API_VERSION, "item": _artifact_to_dict(a)}


def _list(run_id: str, status: str | None, limit: int, offset: int) -> dict[str, Any]:
    svc = ArtifactService()
    result = svc.list_by_run(run_id, status=status, limit=limit, offset=offset)
    return _list_response(result["items"], total=result["total"])


def _get(artifact_id: str) -> dict[str, Any]:
    svc = ArtifactService()
    try:
        a = svc.get(artifact_id)
    except ArtifactNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    return {"version": API_VERSION, "item": _artifact_to_dict(a)}


def _verify(artifact_id: str, req: VerifyArtifactRequest) -> dict[str, Any]:
    svc = ArtifactService()
    try:
        a = svc.verify(artifact_id, verified_by=req.verified_by, verified_result=req.verified_result,
                       expected_revision=req.expected_revision)
    except ArtifactNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except ArtifactConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    return {"version": API_VERSION, "item": _artifact_to_dict(a)}


def _accept(artifact_id: str, req: AcceptArtifactRequest) -> dict[str, Any]:
    svc = ArtifactService()
    try:
        a = svc.accept(artifact_id, accepted_by=req.accepted_by, accepted_note=req.accepted_note,
                       expected_revision=req.expected_revision)
    except ArtifactNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except ArtifactConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    return {"version": API_VERSION, "item": _artifact_to_dict(a)}


def _reject(artifact_id: str, req: RejectArtifactRequest) -> dict[str, Any]:
    svc = ArtifactService()
    try:
        a = svc.reject(artifact_id, rejected_by=req.rejected_by, reason=req.reason,
                       expected_revision=req.expected_revision)
    except ArtifactNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except ArtifactConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    return {"version": API_VERSION, "item": _artifact_to_dict(a)}


@router.post("", response_model=None)
async def create_artifact(req: CreateArtifactRequest) -> dict[str, Any]:
    return await asyncio.to_thread(_create, req)


@router.get("", response_model=None)
async def list_artifacts(
    run_id: str = Query(..., min_length=1, max_length=40),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return await asyncio.to_thread(_list, run_id, status, limit, offset)


@router.get("/{artifact_id}", response_model=None)
async def get_artifact(artifact_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_get, artifact_id)


@router.post("/{artifact_id}/verify", response_model=None)
async def verify_artifact(
    artifact_id: str, req: VerifyArtifactRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_verify, artifact_id, req)


@router.post("/{artifact_id}/accept", response_model=None)
async def accept_artifact(
    artifact_id: str, req: AcceptArtifactRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_accept, artifact_id, req)


@router.post("/{artifact_id}/reject", response_model=None)
async def reject_artifact(
    artifact_id: str, req: RejectArtifactRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_reject, artifact_id, req)

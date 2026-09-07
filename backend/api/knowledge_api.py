"""v1.0 T13 Knowledge API (contracts §9 + §0.4) + C12 R16 adoption API.

路由清单 (前缀 /api/v1/knowledge)
--------
- ``POST /api/v1/knowledge/generate``     dsh 调 knowledge_publish 落 draft
- ``GET  /api/v1/knowledge``              列表 (query: case_id + status/kind/limit/offset)
- ``GET  /api/v1/knowledge/{id}``         详情
- ``GET  /api/v1/knowledge/{id}/reuse``   §9.4 复用记录派生 (C12 R16 改: by_decision/by_outcome)
- ``POST /api/v1/knowledge/{id}/publish``   draft → published (CAS expected_revision)
- ``POST /api/v1/knowledge/{id}/deprecate`` published → deprecated (必填 reason + 可选替代)
- ``POST /api/v1/knowledge/{id}/retract``   published|deprecated → retracted (必填 reason)

C12 R16 (知识采用 + 失效反馈):
- ``POST /api/v1/knowledge/{id}/adopt``     记录一次采用 (decision + condition_diff)
- ``GET  /api/v1/knowledge/{id}/adoptions`` 列出所有 adoptions
- ``POST /api/v1/knowledge/{id}/outcome``   记录采用结果 (success|partial|failure)
- ``GET  /api/v1/knowledge/{id}/recall``    召回 — 条件比较 + adoption history (?case_id=)

错误
----
- ``E_VALIDATION`` (400) / ``E_NOT_FOUND`` (404) / ``E_CONFLICT`` (409)
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.knowledge_service import (
    KnowledgeConflictError,
    KnowledgeNotFoundError,
    KnowledgeService,
    KnowledgeValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/knowledge", tags=["v1-knowledge"])


class GenerateKnowledgeRequest(BaseModel):
    """POST /api/v1/knowledge/generate — dsh 调 knowledge_publish 落 draft."""

    case_id: str = Field(min_length=1, max_length=26)
    judgment_id: str = Field(min_length=1, max_length=26)
    action_id: str = Field(min_length=1, max_length=40)
    subject_name: str = Field(min_length=1, max_length=200)
    cve_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(pattern="^(principle|pattern|anti_pattern|reference|playbook|checklist)$")
    evidence_materials: list[dict[str, Any]] = Field(default_factory=list)
    submitted_by: str = Field(default="user")


class StateChangeRequest(BaseModel):
    """POST /api/v1/knowledge/{id}/{publish|deprecate|retract|revive} — body 必含 expected_revision."""

    expected_revision: int = Field(ge=1)


class DeprecateKnowledgeRequest(StateChangeRequest):
    reason: str = Field(min_length=1, max_length=2000)
    replacement_knowledge_id: str | None = None


class RetractKnowledgeRequest(StateChangeRequest):
    reason: str = Field(min_length=1, max_length=2000)


# ---------------------------------------------------------------------------
# C12 R16 — 知识采用 (adopt / outcome) + 召回 (recall)
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


def _knowledge_to_dict(k: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": k["id"],
        "kind": k["kind"],
        "title": k["title"],
        "body": k["body"],
        "prerequisites": k.get("prerequisites", []),
        "counter_examples": k.get("counter_examples", []),
        "evidence_refs": k.get("evidence_refs", []),
        "expiry_at": k.get("expiry_at"),
        "review_at": k.get("review_at"),
        "status": k["status"],
        "revision": k["revision"],
        "wiki_path": k.get("wiki_path"),
        "content_hash": k.get("content_hash"),
        "published_at": k.get("published_at"),
        "deprecation_reason": k.get("deprecation_reason"),
        "replacement_knowledge_id": k.get("replacement_knowledge_id"),
        "retraction_reason": k.get("retraction_reason"),
        "allowed_actions": k.get("allowed_actions", []),
        "reason": k.get("reason"),
        "created_at": k["created_at"],
        "updated_at": k["updated_at"],
    }


def _list_response(items: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {
        "version": API_VERSION,
        "items": [_knowledge_to_dict(k) for k in items],
        "total": total if total is not None else len(items),
    }


def _generate(req: GenerateKnowledgeRequest) -> dict[str, Any]:
    svc = KnowledgeService()
    try:
        result = svc.create_with_dsh(
            case_id=req.case_id, judgment_id=req.judgment_id, action_id=req.action_id,
            subject_name=req.subject_name, cve_id=req.cve_id, kind=req.kind,
            evidence_materials=req.evidence_materials, submitted_by=req.submitted_by,
        )
    except KnowledgeValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    except KnowledgeConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    return {
        "version": API_VERSION,
        "item": _knowledge_to_dict(result["knowledge"]),
        "idempotent_replay": result["idempotent_replay"],
    }


def _list(case_id: str | None, status: str | None, kind: str | None, limit: int, offset: int) -> dict[str, Any]:
    """T15.5: case_id=None 走 list_all (全局), 非 None 走 list_by_case (T13 路径)."""
    svc = KnowledgeService()
    if case_id is None:
        result = svc.list_all(status=status, kind=kind, limit=limit, offset=offset)
    else:
        result = svc.list_by_case(case_id, status=status, kind=kind, limit=limit, offset=offset)
    return _list_response(result["items"], total=result["total"])


def _get(knowledge_id: str) -> dict[str, Any]:
    svc = KnowledgeService()
    try:
        k = svc.get(knowledge_id)
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    return {"version": API_VERSION, "item": _knowledge_to_dict(k)}


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


# ---------------------------------------------------------------------------
# C12 R16 handlers
# ---------------------------------------------------------------------------
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
    from backend.repository.db import get_connection
    svc = KnowledgeService()
    # 验证存在性
    try:
        svc.get(knowledge_id)
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, case_id, knowledge_revision, decision, condition_diff_json, "
        "outcome, outcome_note, adopted_at, adopted_by, decided_by "
        "FROM v1_knowledge_adoptions WHERE knowledge_id = ? "
        "ORDER BY adopted_at DESC",
        (knowledge_id,),
    ).fetchall()
    import json
    items: list[dict[str, Any]] = []
    for r in rows:
        try:
            diff = json.loads(r[4]) if r[4] else []
        except (json.JSONDecodeError, TypeError):
            diff = []
        items.append({
            "id": r[0], "case_id": r[1], "knowledge_revision": r[2],
            "decision": r[3], "condition_diff": diff,
            "outcome": r[5], "outcome_note": r[6],
            "adopted_at": r[7], "adopted_by": r[8], "decided_by": r[9],
        })
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


def _recall(knowledge_id: str, case_id: str) -> dict[str, Any]:
    svc = KnowledgeService()
    try:
        result = svc.recall_for_case(case_id, knowledge_id=knowledge_id)
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except KnowledgeValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    return {"version": API_VERSION, "recall": result}


def _publish(knowledge_id: str, req: StateChangeRequest) -> dict[str, Any]:
    svc = KnowledgeService()
    try:
        k = svc.publish(knowledge_id, expected_revision=req.expected_revision)
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except KnowledgeConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    except KnowledgeValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    return {"version": API_VERSION, "item": _knowledge_to_dict(k)}


def _deprecate(knowledge_id: str, req: DeprecateKnowledgeRequest) -> dict[str, Any]:
    svc = KnowledgeService()
    try:
        k = svc.deprecate(
            knowledge_id, expected_revision=req.expected_revision, reason=req.reason,
            replacement_knowledge_id=req.replacement_knowledge_id,
        )
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except KnowledgeConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    return {"version": API_VERSION, "item": _knowledge_to_dict(k)}


def _retract(knowledge_id: str, req: RetractKnowledgeRequest) -> dict[str, Any]:
    svc = KnowledgeService()
    try:
        k = svc.retract(knowledge_id, expected_revision=req.expected_revision, reason=req.reason)
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except KnowledgeConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    return {"version": API_VERSION, "item": _knowledge_to_dict(k)}


@router.post("/generate", response_model=None)
async def generate_knowledge(req: GenerateKnowledgeRequest) -> dict[str, Any]:
    return await asyncio.to_thread(_generate, req)


@router.get("", response_model=None)
async def list_knowledge(
    case_id: str | None = Query(None, max_length=26),
    status: str | None = Query(None),
    kind: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """T15.5: case_id 可选, None 走 list_all (全局)."""
    return await asyncio.to_thread(_list, case_id, status, kind, limit, offset)


@router.get("/{knowledge_id}", response_model=None)
async def get_knowledge(knowledge_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_get, knowledge_id)


@router.get("/{knowledge_id}/reuse", response_model=None)
async def get_knowledge_reuse(knowledge_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_reuse, knowledge_id)


@router.post("/{knowledge_id}/publish", response_model=None)
async def publish_knowledge(
    knowledge_id: str, req: StateChangeRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_publish, knowledge_id, req)


@router.post("/{knowledge_id}/deprecate", response_model=None)
async def deprecate_knowledge(
    knowledge_id: str, req: DeprecateKnowledgeRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_deprecate, knowledge_id, req)


@router.post("/{knowledge_id}/retract", response_model=None)
async def retract_knowledge(
    knowledge_id: str, req: RetractKnowledgeRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_retract, knowledge_id, req)


# ---------------------------------------------------------------------------
# C12 R16 — 知识采用 / 结果 / 召回 路由
# ---------------------------------------------------------------------------
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


@router.get("/{knowledge_id}/recall", response_model=None)
async def recall_knowledge_for_case(
    knowledge_id: str, case_id: str = Query(..., min_length=1, max_length=26),
) -> dict[str, Any]:
    """召回: 该 knowledge 对给定 case 的适用性 + 条件比较 + adoption 历史."""
    return await asyncio.to_thread(_recall, knowledge_id, case_id)

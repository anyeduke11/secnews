"""MP-2 Event Technique API — /api/event-technique/* (6 端点).

Endpoints
---------
- GET  /api/event-technique/candidates                    — 候选列表 (按 event_type 过滤)
- POST /api/event-technique/candidates                    — 候选手工补录 (脚本/修复用)
- POST /api/event-technique/candidates/{id}/approve       — owner approve → 落 map
- POST /api/event-technique/candidates/{id}/reject        — owner reject (须 reason)
- GET  /api/event-technique/event-types                   — 事件类型清单 (含进度统计)
- GET  /api/event-technique/event-types/{id}/techniques   — 技战法链 (已审定, 渲染用)

审计
----
- approve/reject/batch 全部写 audit_log_mp2_review (actor=owner)
- candidates POST 为脚本侧入口 (owner_status 一律 pending), 不写 audit
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.exceptions import ConflictException, InvalidParamException, NotFoundException
from backend.repository.event_technique_repo import (
    EventTechniqueCandidateRepo,
    EventTypeRepo,
    new_ulid,
)
from backend.services.attack_label_service import AttackLabelService
from backend.services.event_technique_extract_service import CONFIDENCE_THRESHOLD
from backend.services.event_technique_review_service import EventTechniqueReviewService

router = APIRouter(prefix="/api/event-technique", tags=["event-technique"])

_candidate_repo = EventTechniqueCandidateRepo()
_event_type_repo = EventTypeRepo()
_review_svc = EventTechniqueReviewService()
_label_svc = AttackLabelService()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CandidateIn(BaseModel):
    event_type_id: str
    technique_id: str
    stage: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quote: str = Field(max_length=500)
    rationale: str | None = None
    source_report_id: str
    llm_model: str = "manual"
    agent_owner: str = "A"


class RejectIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    owner: str = "owner"


class ApproveIn(BaseModel):
    note: str | None = None
    owner: str = "owner"


class BatchApproveIn(BaseModel):
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    owner: str = "owner"
    note: str | None = None


def _http_exc(e: Exception) -> HTTPException:
    """项目异常 → HTTP 异常映射 (503/400/409/404)."""
    if isinstance(e, NotFoundException):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, InvalidParamException):
        return HTTPException(status_code=400, detail=str(e))
    if isinstance(e, ConflictException):
        return HTTPException(status_code=409, detail=str(e))
    return HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 1) GET /candidates — 候选列表
# ---------------------------------------------------------------------------
@router.get("/candidates")
def list_candidates(
    event_type_id: str = Query(..., description="事件类型 id (evt_ransomware 等)"),
    owner_status: str | None = Query(None, description="pending/approved/rejected"),
    limit: int = Query(200, ge=1, le=500),
):
    try:
        items = _candidate_repo.list_by_event_type(event_type_id, owner_status, limit)
        return {"event_type_id": event_type_id, "owner_status": owner_status, "total": len(items), "items": items}
    except Exception as e:
        raise _http_exc(e) from e


# ---------------------------------------------------------------------------
# 2) POST /candidates — 手工补录 (脚本/修复用, 一律 pending)
# ---------------------------------------------------------------------------
@router.post("/candidates")
def create_candidate(body: CandidateIn):
    try:
        et = _event_type_repo.get(body.event_type_id)
        if not et:
            raise NotFoundException(f"event_type {body.event_type_id} not found")
        if body.confidence < CONFIDENCE_THRESHOLD:
            raise InvalidParamException(
                f"confidence {body.confidence} < {CONFIDENCE_THRESHOLD} (不入候选池)"
            )
        cid = new_ulid("etc")
        _candidate_repo.insert(
            candidate_id=cid,
            event_type_id=body.event_type_id,
            technique_id=body.technique_id,
            stage=body.stage,
            confidence=body.confidence,
            evidence_quote=body.evidence_quote,
            rationale=body.rationale,
            source_report_id=body.source_report_id,
            llm_model=body.llm_model,
            llm_run_at=datetime.now(timezone.utc).isoformat(),
            agent_owner=body.agent_owner,
        )
        return {"id": cid, "owner_status": "pending"}
    except Exception as e:
        raise _http_exc(e) from e


# ---------------------------------------------------------------------------
# 3) POST /candidates/{id}/approve
# ---------------------------------------------------------------------------
@router.post("/candidates/{candidate_id}/approve")
def approve_candidate(candidate_id: str, body: ApproveIn):
    try:
        return _review_svc.approve_candidate(candidate_id, owner=body.owner, note=body.note)
    except Exception as e:
        raise _http_exc(e) from e


# ---------------------------------------------------------------------------
# 4) POST /candidates/{id}/reject
# ---------------------------------------------------------------------------
@router.post("/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str, body: RejectIn):
    try:
        return _review_svc.reject_candidate(candidate_id, owner=body.owner, reject_reason=body.reason)
    except Exception as e:
        raise _http_exc(e) from e


# ---------------------------------------------------------------------------
# 5) POST /event-types/{id}/batch-approve — 批量便利 (挂在 event-types 下, 不计入 6 端点)
#    + GET /event-types — 清单 (含进度)
# ---------------------------------------------------------------------------
@router.get("/event-types")
def list_event_types(category: str | None = None):
    try:
        items = _event_type_repo.list_all(category=category)
        progress = _review_svc.get_progress()
        prog_map = {g["event_type_id"]: g for g in progress["by_event_type"]}
        for it in items:
            g = prog_map.get(it["id"], {})
            it["candidate_stats"] = {
                "pending": g.get("pending", 0),
                "approved": g.get("approved", 0),
                "rejected": g.get("rejected", 0),
                "total": g.get("total", 0),
                "avg_confidence": round(g.get("avg_confidence") or 0, 3),
                "approved_map": g.get("approved_map", 0),
            }
        return {"total": len(items), "items": items}
    except Exception as e:
        raise _http_exc(e) from e


@router.post("/event-types/{event_type_id}/batch-approve")
def batch_approve(event_type_id: str, body: BatchApproveIn):
    try:
        return _review_svc.batch_approve_for_event_type(
            event_type_id, owner=body.owner, min_confidence=body.min_confidence, note=body.note
        )
    except Exception as e:
        raise _http_exc(e) from e


# ---------------------------------------------------------------------------
# 6) GET /event-types/{id}/techniques — 技战法链 (已审定)
# ---------------------------------------------------------------------------
@router.get("/event-types/{event_type_id}/techniques")
def get_technique_chain(event_type_id: str):
    try:
        return _label_svc.get_event_techniques_for_type(event_type_id)
    except Exception as e:
        raise _http_exc(e) from e


__all__ = ["router"]

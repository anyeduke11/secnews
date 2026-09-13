"""MP-2 Event Technique API — /api/event-technique/candidates (4 端点).

Endpoints
---------
- GET  /api/event-technique/candidates   — 候选列表 (按 event_type 过滤)
- POST /api/event-technique/candidates   — 候选手工补录 (脚本/修复用)

审计
----
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
from backend.services.event_technique_extract_service import CONFIDENCE_THRESHOLD

router = APIRouter(prefix="/api/event-technique", tags=["event-technique"])

_candidate_repo = EventTechniqueCandidateRepo()
_event_type_repo = EventTypeRepo()


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


__all__ = ["router"]

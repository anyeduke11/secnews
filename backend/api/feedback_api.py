"""v0.7 Batch ⑤ + 设置画像 — Feedback API.

Endpoints
---------
- POST /api/feedback/          — submit like/dislike
- GET  /api/feedback/profile   — feedback profile summary
- GET  /api/feedback/history   — full feedback history (settings page)
- GET  /api/feedback/role-summary — role tendency summary (settings page)
- GET  /api/feedback/entity/{entity_type}/{entity_id} — entity history
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.services.feedback_service import FeedbackService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])
_feedback_service = FeedbackService()


class FeedbackRequest(BaseModel):
    entity_type: str = Field(..., description="hotspot or knowledge")
    entity_id: str = Field(..., description="Entity ID")
    action: str = Field(..., description="like or dislike")


class FeedbackResponse(BaseModel):
    ok: bool
    action: str
    signal: float
    weights: dict[str, float]
    event_id: int | None = None


@router.post("/", response_model=FeedbackResponse)
async def post_feedback(request: Request, body: FeedbackRequest) -> dict[str, Any]:
    """Submit like/dislike feedback for an entity."""
    if body.action not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="invalid action: must be 'like' or 'dislike'")
    if body.entity_type not in ("hotspot", "knowledge"):
        raise HTTPException(status_code=400, detail="invalid entity_type: must be 'hotspot' or 'knowledge'")

    def _run():
        return _feedback_service.submit_feedback(
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            action=body.action,
        )

    return await asyncio.to_thread(_run)


@router.get("/profile")
async def get_feedback_profile(limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    """Get user feedback profile summary."""
    def _run():
        return _feedback_service.get_feedback_profile(limit=limit)

    return await asyncio.to_thread(_run)


@router.get("/entity/{entity_type}/{entity_id}")
async def get_entity_feedback(entity_type: str, entity_id: str) -> dict[str, Any]:
    """Get feedback history for a specific entity."""
    if entity_type not in ("hotspot", "knowledge"):
        raise HTTPException(status_code=400, detail="invalid entity_type: must be 'hotspot' or 'knowledge'")

    def _run():
        items = _feedback_service.get_entity_feedback(entity_type, entity_id)
        return {"entity_id": entity_id, "entity_type": entity_type, "items": items}

    return await asyncio.to_thread(_run)


@router.get("/history")
async def get_feedback_history(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    """Get full feedback history for settings page."""
    def _run():
        return _feedback_service.get_feedback_history(limit=limit)

    return await asyncio.to_thread(_run)


@router.get("/role-summary")
async def get_role_summary() -> dict[str, Any]:
    """Get role tendency summary based on feedback history."""
    def _run():
        return _feedback_service.get_role_summary()

    return await asyncio.to_thread(_run)

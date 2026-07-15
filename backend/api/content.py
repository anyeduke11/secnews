"""Content API — calendar + drafts + templates (v1.4 Group K)."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.services import content_service

log = logging.getLogger("hotspot.api.content")
router = APIRouter(prefix="/api/content", tags=["content"])


# ── Calendar ───────────────────────────────────────────────────

@router.get("/calendar")
async def list_calendar(month: Optional[str] = Query(None)):
    """List calendar entries, optionally filtered by ?month=YYYY-MM."""
    entries = content_service.list_calendar(month)
    return {"entries": entries}


@router.post("/calendar")
async def create_calendar_entry(data: dict):
    """Create a calendar entry. Body: {date, topic, type?, source_items?, platform?}."""
    date = data.get("date")
    topic = data.get("topic")
    if not date or not topic:
        raise HTTPException(status_code=400, detail="date and topic are required")
    return content_service.create_calendar_entry(
        date=date,
        topic=topic,
        type=data.get("type"),
        source_items=data.get("source_items"),
        platform=data.get("platform"),
    )


@router.patch("/calendar/{entry_id}")
async def update_calendar_entry(entry_id: int, data: dict):
    """Update a calendar entry. Body: any subset of updatable fields."""
    try:
        return content_service.update_calendar_entry(entry_id, **data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/calendar/{entry_id}")
async def delete_calendar_entry(entry_id: int):
    """Delete a calendar entry."""
    try:
        return content_service.delete_calendar_entry(entry_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Drafts ─────────────────────────────────────────────────────

@router.get("/drafts")
async def list_drafts(
    status: Optional[str] = Query(None),
    calendar_id: Optional[int] = Query(None),
):
    """List drafts, optionally filtered by status or calendar_id."""
    drafts = content_service.list_drafts(status=status, calendar_id=calendar_id)
    return {"drafts": drafts}


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: int):
    """Get a single draft with Markdown content."""
    draft = content_service.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.post("/drafts")
async def create_draft(data: dict):
    """Create a draft. Body: {title, content, calendar_id?}."""
    title = data.get("title")
    content = data.get("content", "")
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    return content_service.create_draft(
        title=title,
        content=content,
        calendar_id=data.get("calendar_id"),
    )


@router.patch("/drafts/{draft_id}")
async def update_draft(draft_id: int, data: dict):
    """Update a draft. Body: any subset of {title, content, status}."""
    try:
        return content_service.update_draft(
            draft_id,
            content=data.get("content"),
            title=data.get("title"),
            status=data.get("status"),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: int):
    """Delete a draft and its .md file."""
    try:
        return content_service.delete_draft(draft_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Templates ──────────────────────────────────────────────────

@router.get("/templates")
async def list_templates():
    """List the 7 preset content templates."""
    return {"templates": content_service.list_templates()}


# ── Publish ─────────────────────────────────────────────────────

@router.post("/drafts/{draft_id}/publish")
async def publish_draft(draft_id: int, data: dict):
    """Create a publish task for a draft.

    Body: {platform, skill_name, options?}
    """
    platform = data.get("platform")
    skill_name = data.get("skill_name")
    if not platform or not skill_name:
        raise HTTPException(
            status_code=400, detail="platform and skill_name are required"
        )
    try:
        return content_service.create_publish_task(
            draft_id=draft_id,
            platform=platform,
            skill_name=skill_name,
            options=data.get("options"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/drafts/{draft_id}/publish-history")
async def get_publish_history(draft_id: int):
    """Get publish task history for a draft."""
    history = content_service.get_publish_history(draft_id)
    return {"draft_id": draft_id, "history": history}

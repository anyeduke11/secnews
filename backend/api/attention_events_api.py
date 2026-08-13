"""Attention events API — 追踪用户对知识条目的注意力行为.

端点
----
- ``POST /api/attention/events``  记录注意力事件 (view/dwell/scroll/...)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.logging_config import logger
from backend.repository.db import get_connection

router = APIRouter(prefix="/api", tags=["attention"])

VALID_EVENT_TYPES = frozenset({
    "view",
    "dwell",
    "scroll",
    "favorite",
    "annotation",
    "share",
})


class AttentionEventRequest(BaseModel):
    """注意力事件请求体。"""
    item_id: str = Field(..., description="知识条目 ID")
    event_type: str = Field(
        ..., description="事件类型: view/dwell/scroll/favorite/annotation/share"
    )
    detail_json: dict = Field(
        default_factory=dict, description="事件详情 (可选)"
    )


@router.post("/attention/events", status_code=201)
async def create_attention_event(req: AttentionEventRequest) -> dict:
    """记录一条注意力事件.

    校验 event_type 为 6 种合法值之一, 写入 attention_events 表。
    返回 201 + ``{success: true, event_id: int}``。
    非法 event_type 返回 400。
    """
    if req.event_type not in VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    f"event_type 必须为 {sorted(VALID_EVENT_TYPES)}; "
                    f"got {req.event_type!r}"
                )
            },
        )

    detail_text = json.dumps(req.detail_json, ensure_ascii=False)
    created_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO attention_events "
            "(item_id, event_type, detail_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (req.item_id, req.event_type, detail_text, created_at),
        )
        event_id = cursor.lastrowid
    except Exception as e:
        logger.error(f"insert attention_event failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={"message": f"写入注意力事件失败: {e}"},
        )

    return {"success": True, "event_id": event_id}


__all__ = ["router"]
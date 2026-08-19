"""Attention events API — 追踪用户对知识条目的注意力行为.

端点
----
- ``POST /api/attention/events``  记录注意力事件 (view/dwell/scroll/...)
- ``GET  /api/attention/events``  最近 N 天按 天×小时 聚合 (热力图数据源)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
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

    # P3-1: 知识条目的 view/dwell/favorite 事件 → 自动创建 SM-2 复习记录
    # (此前 create_review 无任何调用点, sm2_reviews 恒 0 → 复习功能死代码)
    # v0.4.3 复利驱动器④: dwell 事件需 dwell_seconds > 30 才转化 (深度阅读判定),
    # view/favorite 保持原有即时转化; create_review 内部幂等 (已存在则返回现有)。
    dwell_seconds = int(req.detail_json.get("dwell_seconds", 0) or 0)
    if req.event_type == "dwell" and dwell_seconds <= 30:
        return {"success": True, "event_id": event_id}
    if req.event_type in ("view", "dwell", "favorite"):
        try:
            _c = get_connection()
            exists = _c.execute(
                "SELECT 1 FROM knowledge_items WHERE id = ?",
                (req.item_id,),
            ).fetchone()
            if exists:
                from backend.services.review_service import create_review
                create_review(entity_type="knowledge_item", entity_id=req.item_id)
        except Exception as e:
            logger.warning(f"auto-create sm2 review failed: {e}")

    return {"success": True, "event_id": event_id}


@router.get("/attention/events")
async def list_attention_events(
    days: int = Query(
        30, ge=1, le=365, description="返回最近 N 天的注意力聚合 (默认 30)"
    ),
) -> dict:
    """返回最近 N 天按 天×小时 聚合的注意力事件.

    Phase 17 热力图数据源: 前端 ``AttentionHeatmap.tsx`` 请求
    ``GET /api/attention/events?days=30``, 期望结构
    ``{ events: [{date: "YYYY-MM-DD", hour: 0-23, count: N}] }``
    (也兼容直接返回数组)。按 ``created_at`` 的日期 + 小时分组计数,
    表为空时返回空列表 ``{"events": []}``。
    """
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT substr(created_at, 1, 10) AS date,
               CAST(substr(created_at, 12, 2) AS INTEGER) AS hour,
               COUNT(*) AS count
        FROM attention_events
        WHERE created_at >= ?
        GROUP BY date, hour
        ORDER BY date, hour
        """,
        (cutoff,),
    ).fetchall()
    events = [
        {"date": r["date"], "hour": r["hour"], "count": r["count"]}
        for r in rows
    ]
    return {"events": events}


__all__ = ["router"]
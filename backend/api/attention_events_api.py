"""Attention events API — 追踪用户对知识条目的注意力行为.

端点
----
- ``POST /api/attention/events``  记录注意力事件 (view/dwell/scroll/...)
- ``GET  /api/attention/events``  最近 N 天按 天×小时 聚合 (热力图数据源)

Batch 2 SQL 下沉: 读写全部经 backend.services.attention_events_service,
本路由仅保留 HTTP 语义 (校验/状态码映射).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.logging_config import logger
from backend.services.attention_events_service import (
    VALID_EVENT_TYPES,
    heatmap_by_day_hour,
    maybe_create_sm2_review,
    record_event,
)

router = APIRouter(prefix="/api", tags=["attention"])


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
def create_attention_event(req: AttentionEventRequest) -> dict:
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

    try:
        event_id = record_event(req.item_id, req.event_type, req.detail_json)
    except Exception as e:
        logger.error(f"insert attention_event failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={"message": f"写入注意力事件失败: {e}"},
        )

    # P3-1: view/dwell/favorite 事件 → 自动创建 SM-2 复习记录 (幂等);
    # dwell 需 dwell_seconds > 30 才转化 — 转化判定在 service 内.
    maybe_create_sm2_review(req.event_type, req.item_id, req.detail_json)

    return {"success": True, "event_id": event_id}


@router.get("/attention/events")
def list_attention_events(
    days: int = Query(
        30, ge=1, le=365, description="返回最近 N 天的注意力聚合 (默认 30)"
    ),
) -> dict:
    """返回最近 N 天按 天×小时 聚合的注意力事件.

    Phase 17 热力图数据源: 前端 ``AttentionHeatmap.tsx`` 请求
    ``GET /api/attention/events?days=30``, 期望结构
    ``{events: [{date: "YYYY-MM-DD", hour: 0-23, count: N}]}``
    (也兼容直接返回数组)。表为空时返回空列表 ``{"events": []}``。
    """
    return {"events": heatmap_by_day_hour(days)}


__all__ = ["router"]

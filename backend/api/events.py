"""SSE 事件总线 — 采集完成后推送实时通知。

Phase 6 (v1.3.0): 采集完成后推送到前端，替代轮询。

用法
----
- 前端连接 ``GET /api/events`` 获取 SSE 流
- 后端调用 ``publish_event("collect_done", data)`` 推送事件
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger("hotspot.api.events")
router = APIRouter(prefix="/api", tags=["events"])

# 订阅者队列池
_subscribers: list[asyncio.Queue] = []
_MAX_SUBSCRIBERS = 50
_QUEUE_MAXSIZE = 100


async def publish_event(event_type: str, data: dict[str, Any]) -> None:
    """向所有订阅者广播事件。"""
    payload = json.dumps(
        {
            "type": event_type,
            "data": data,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
        ensure_ascii=False,
    )
    dead: list[asyncio.Queue] = []
    for q in _subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.remove(q)
    logger.debug(f"published event {event_type!r} to {len(_subscribers)} subscribers")


@router.get("/events")
async def sse_events(request: Request):
    """SSE 事件流端点。

    前端连接此端点后，后端通过 ``publish_event()`` 推送事件。

    自动超时：30 秒无事件时发送 keepalive。
    """

    queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    _subscribers.append(queue)
    if len(_subscribers) > _MAX_SUBSCRIBERS:
        _subscribers.pop(0)

    async def event_stream():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive — 防止代理/浏览器断开连接
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in _subscribers:
                _subscribers.remove(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


__all__ = ["router", "publish_event"]
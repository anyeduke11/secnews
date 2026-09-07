"""SSE 事件总线 — 采集完成后推送实时通知 + C11 R18 outbox 持久重放。

Phase 6 (v1.3.0): 采集完成后推送到前端，替代轮询。
C11 R18: SSE 事件双源 (in-process queue + v1_outbox 重放) — 前端断线重连用
``?last_id=N`` 续传, 不漏不重; 每条事件带 ``id: <outbox.id>``.

用法
----
- 前端连接 ``GET /api/events?last_id=N`` 获取 SSE 流
- 后端调用 ``publish_event("collect_done", data)`` 进程内广播
- 业务写 outbox 行 → 后台 dispatcher 轮询 → 同样通过 publish_event 广播
- 客户端断线重连时, 传 last_id=上次最后一条 SSE id, 自动重放未确认段
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger("hotspot.api.events")
router = APIRouter(prefix="/api", tags=["events"])

# 订阅者队列池
_subscribers: list[asyncio.Queue] = []
_MAX_SUBSCRIBERS = 50
_QUEUE_MAXSIZE = 100


async def publish_event(event_type: str, data: dict[str, Any], *, outbox_id: int | None = None) -> None:
    """向所有订阅者广播事件。

    C11 R18: 每条事件可附带 outbox 行 id, 客户端断线重连用 last_id 续传.
    """
    payload = json.dumps(
        {
            "id": outbox_id,  # C11 R18: SSE id 字段供 Last-Event-ID
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
    logger.debug(f"published event {event_type!r} (id={outbox_id}) to {len(_subscribers)} subscribers")


@router.get("/events")
async def sse_events(
    request: Request,
    last_id: int = Query(default=0, ge=0, description="C11 R18: 上次最后一条 SSE id, 续传未确认段"),
):
    """SSE 事件流端点。

    - 进程内事件实时推送 (publish_event 调度的)
    - 启动时 (C11 R18): 先用 last_id 重放 outbox 历史, 再进入 live 模式
    - 自动超时: 30 秒无事件时发送 keepalive
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    _subscribers.append(queue)
    if len(_subscribers) > _MAX_SUBSCRIBERS:
        _subscribers.pop(0)

    async def event_stream():
        try:
            # C11 R18: 启动时回放 last_id 之后的所有 outbox 行
            if last_id > 0:
                try:
                    from backend.repository.outbox_repo import OutboxRepo
                    replay = OutboxRepo().list_since(last_id, limit=200)
                    for row in replay:
                        payload = json.dumps(
                            {
                                "id": row["id"],
                                "type": row["event_type"],
                                "data": row["payload"],
                                "ts": row["occurred_at"],
                            },
                            ensure_ascii=False,
                            default=str,
                        )
                        yield f"id: {row['id']}\nevent: {row['event_type']}\ndata: {payload}\n\n"
                except Exception as e:
                    logger.warning(f"SSE replay failed (last_id={last_id}): {e}")

            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    # 解析出 id (如果有) 加 SSE id 字段
                    try:
                        obj = json.loads(data)
                        eid = obj.get("id")
                        if eid is not None:
                            yield f"id: {eid}\ndata: {data}\n\n"
                        else:
                            yield f"data: {data}\n\n"
                    except Exception:
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


__all__ = ["publish_event", "router"]
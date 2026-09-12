"""SSE 端点 — 事件总线已下沉 ``backend/core/events.py`` (DEV-0191)。

本模块只保留 HTTP 关注点: ``GET /api/events?last_id=N`` 订阅流 +
C11 R18 outbox 断线重放。进程内广播 (publish_event / 订阅池) 见
``backend/core/events.py`` — services 与 scheduler 从那里导入,
禁止再 import 本模块发布事件 (test_layering_guard.py 机械断言)。

Phase 6 (v1.3.0): 采集完成后推送到前端，替代轮询。
C11 R18: SSE 事件双源 (in-process queue + v1_outbox 重放) — 前端断线重连用
``?last_id=N`` 续传, 不漏不重; 每条事件带 ``id: <outbox.id>``.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from backend.core.events import subscribe, unsubscribe
from backend.logging_config import logger

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def sse_events(
    request: Request,
    last_id: int = Query(default=0, ge=0, description="C11 R18: 上次最后一条 SSE id, 续传未确认段"),
):
    """SSE 事件流端点。

    - 进程内事件实时推送 (core.events.publish_event 调度的)
    - 启动时 (C11 R18): 先用 last_id 重放 outbox 历史, 再进入 live 模式
    - 自动超时: 30 秒无事件时发送 keepalive
    """
    queue = subscribe()

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
            unsubscribe(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


__all__ = ["router"]

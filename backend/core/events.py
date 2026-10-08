"""进程内 SSE 事件总线 — 自 ``backend/api/events.py`` 下沉 (DEV-0191)。

事件总线是基础设施, 不属于 API 层: 此前 services / scheduler 发布事件
必须 ``from backend.api.events import publish_event``, 造成 8 处
services→api 反向依赖, 分层禁令「service 层禁 import backend.api」
无法机械执行。下沉后:

- 业务侧统一 ``from backend.core.events import publish_event``
- API 层 (api/events.py) 只保留 ``GET /api/events`` SSE 端点 +
  outbox 重放 (C11 R18), 通过 subscribe()/unsubscribe() 接入总线
- test_layering_guard.py 全量断言 services/scheduler/collectors/
  repository 四层不再 import backend.api

行为不变: 订阅池容量 / 满队列剔除 / payload 形状 (id/type/data/ts)
全部照搬原实现, 仅日志从 stdlib logging 换 loguru (全仓规则: stdlib
logging 无 InterceptHandler 不可见)。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from backend.logging_config import logger

# 订阅者队列池 (api/events.py 的 SSE 端点经 subscribe()/unsubscribe() 接入)
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


def subscribe() -> asyncio.Queue:
    """注册一个订阅者队列 (SSE 端点每个连接调用一次), 超上限时淘汰最老订阅者."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    _subscribers.append(queue)
    if len(_subscribers) > _MAX_SUBSCRIBERS:
        _subscribers.pop(0)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    """移除订阅者 (连接断开时调用); 容忍已被满队列剔除的队列."""
    if queue in _subscribers:
        _subscribers.remove(queue)


# DEV-0302 R1: 停机哨兵 — lifespan shutdown 首步置位, SSE 流的
# queue.get 等待循环在下一个轮询点 (≤KEEPALIVE_INTERVAL_S) 自行终结,
# 让 uvicorn 排空阶段 (timeout_graceful_shutdown) 在秒级走完而非吃满。
_shutdown_requested = False


def request_shutdown() -> None:
    """置停机哨兵并唤醒所有 SSE 订阅者 (lifespan shutdown 首步调用)。"""
    global _shutdown_requested
    _shutdown_requested = True
    for q in list(_subscribers):
        try:
            q.put_nowait('{"type": "server_shutdown"}')
        except asyncio.QueueFull:
            pass


def is_shutdown_requested() -> bool:
    return _shutdown_requested


__all__ = [
    "is_shutdown_requested",
    "publish_event",
    "request_shutdown",
    "subscribe",
    "unsubscribe",
]

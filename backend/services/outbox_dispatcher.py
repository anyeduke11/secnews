"""C11 R18: OutboxDispatcher — 业务 outbox 行 → SSE 广播。

设计
----
- 后台 task 每 1s 轮询 v1_outbox (delivered_at IS NULL), 取未广播段
- 调 events.publish_event(event_type, payload, outbox_id=row['id']) 广播
- 全部成功 → mark_delivered(ids); 失败保留 NULL (下次重试)
- C6-2: add_handler 注册的业务订阅钩子在广播成功后 fire-and-forget 执行
  (独立线程, 失败不回收 delivered 语义)
- 启动入口: main.py lifespan
- 关闭: cancel task + 等待最后一批 flush
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("hotspot.outbox_dispatcher")

_POLL_INTERVAL_SECONDS = 1.0
_BATCH_SIZE = 50


class OutboxDispatcher:
    """C11 R18: 业务 outbox → SSE 广播 dispatcher."""

    def __init__(self, *, poll_interval: float = _POLL_INTERVAL_SECONDS, batch_size: int = _BATCH_SIZE):
        self._poll_interval = float(poll_interval)
        self._batch_size = int(batch_size)
        self._task: asyncio.Task | None = None
        self._stop = False
        self._handlers: dict[str, list[Callable[[dict], Any]]] = {}
        self._handler_tasks: set[asyncio.Task] = set()

    def add_handler(self, event_type: str, handler: Callable[[dict], Any]) -> None:
        """C6-2: 订阅钩子 — 该 event_type 广播成功后异步跑 handler(row)。

        handler 在独立线程执行 (同步 DB/LLM 不阻塞 SSE 广播), fire-and-forget:
        失败只 warning 留痕, 不改 delivered 语义; 幂等由 handler 自己保证
        (同一 outbox 行可能因重启重放)。
        """
        self._handlers.setdefault(event_type, []).append(handler)

    async def start(self) -> None:
        """启动后台轮询 task; 重复调用幂等."""
        if self._task and not self._task.done():
            return
        self._stop = False
        self._task = asyncio.create_task(self._run_loop(), name="outbox-dispatcher")
        logger.info("outbox dispatcher started (poll_interval=%.1fs batch=%d)", self._poll_interval, self._batch_size)

    async def stop(self) -> None:
        """停止后台 task; 等待最后一批 flush."""
        self._stop = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        for t in list(self._handler_tasks):
            t.cancel()
        self._handler_tasks.clear()
        logger.info("outbox dispatcher stopped")

    async def flush_once(self) -> int:
        """同步刷一批: 拉未广播 → 广播 → mark_delivered. 返本批广播数.

        测试与 main 启动收口时调用, 不阻塞主路径.
        """
        from backend.core.events import publish_event
        from backend.repository.outbox_repo import OutboxRepo

        repo = OutboxRepo()
        rows = repo.list_undelivered(limit=self._batch_size)
        if not rows:
            return 0
        delivered_ids: list[int] = []
        for row in rows:
            try:
                await publish_event(
                    row["event_type"], row["payload"], outbox_id=row["id"],
                )
                delivered_ids.append(row["id"])
                self._schedule_handlers(row)
            except Exception as e:
                # Mimosa 禁 silent, 但 dispatcher 自身不能因单条失败整体停
                logger.warning(f"outbox broadcast failed for id={row['id']}: {e}")
        if delivered_ids:
            repo.mark_delivered(delivered_ids)
        return len(delivered_ids)

    def _schedule_handlers(self, row: dict) -> None:
        handlers = self._handlers.get(row.get("event_type"))
        if not handlers:
            return
        for handler in handlers:
            task = asyncio.create_task(
                asyncio.to_thread(handler, row),
                name=f"outbox-handler-{row['id']}",
            )
            self._handler_tasks.add(task)
            task.add_done_callback(self._on_handler_done)

    def _on_handler_done(self, task: asyncio.Task) -> None:
        self._handler_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.warning(f"outbox handler failed: {exc}")

    async def _run_loop(self) -> None:
        """主循环: 每 poll_interval 拉一批, 永不抛."""
        while not self._stop:
            try:
                await self.flush_once()
            except Exception as e:
                logger.warning(f"outbox dispatcher tick failed: {e}")
            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break


# 全局单例 (main.py lifespan 启停)
_singleton: OutboxDispatcher | None = None


def get_dispatcher() -> OutboxDispatcher:
    """获取全局 dispatcher 单例 (lazy)."""
    global _singleton
    if _singleton is None:
        _singleton = OutboxDispatcher()
    return _singleton


__all__ = ["OutboxDispatcher", "get_dispatcher"]

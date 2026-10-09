"""MCP SSE 停机终结 (DEV-0306 R10) — /mcp/sse 长连接接入停机哨兵。

问题: R1 只接入了 `/api/events`。MCP 库 (`mcp.server.sse.SseServerTransport`)
的 SSE 流在 `connect_sse` 里 `async for ... in write_stream_reader` 等客户端
POST 消息, 不吃停机哨兵 → 有 MCP 客户端在连时, 每次停机白吃满
`timeout_graceful_shutdown` (15s) 排空预算才被 uvicorn cancel。

方案 (与 R1 哨兵同架构 — 包装而非改库):
- 包装 `SseServerTransport.connect_sse` (基类 patch 自动覆盖
  fastapi-mcp 的 `FastApiSseTransport` 子类)。
- 连接建立时派生一个 closer 任务: 订阅 core/events 总线, 收到
  `server_shutdown` 广播 → `aclose()` 该 transport 全部 session writer →
  库的 `async for` 循环自然终结 → connect_sse 返回 → 排空秒级走完。
- 客户端视角 = SSE 流被关闭, 与既有断连重连语义一致 (MCP 客户端会自行
  重连, 停机场景重连失败即完成断开)。

never-fail: closer/aclose 全部吞异常 — 终结失败退回原生排空兜底 (有界)。
"""
from __future__ import annotations

import asyncio
from typing import Any

from backend.logging_config import logger


def _is_shutdown_message(msg: Any) -> bool:
    return isinstance(msg, str) and '"server_shutdown"' in msg


async def _close_session_writers(transport: Any) -> None:
    """aclose 全部在连 session 的 writer → 各 connect_sse 的读循环终结。"""
    writers = getattr(transport, "_read_stream_writers", None)
    if not writers:
        return
    for writer in list(writers.values()):
        try:
            await writer.aclose()
        except Exception:
            pass  # 已关/竞争 — 不影响其余


async def _shutdown_closer(transport: Any) -> None:
    """等停机哨兵 → 关 writer。哨兵先于连接置位时立即终结。"""
    from backend.core import events as core_events

    if core_events.is_shutdown_requested():
        await _close_session_writers(transport)
        return
    q = core_events.subscribe()
    try:
        while True:
            msg = await q.get()
            if _is_shutdown_message(msg):
                await _close_session_writers(transport)
                return
    finally:
        core_events.unsubscribe(q)


def arm_mcp_sse_sentinel() -> None:
    """包装 SseServerTransport.connect_sse, 使 MCP SSE 吃停机哨兵。

    幂等; mcp 库缺失时静默跳过 (MCP 未启用, 无 SSE 流可终结)。

    形态关键 (实弹 500 教训, DEV-0306): `connect_sse` 是
    `@asynccontextmanager` 装饰的 CM 工厂 — fastapi-mcp 以
    ``async with transport.connect_sse(scope, receive, send) as
    (reader, writer)`` 消费 (server.py L197)。包装必须保持 async CM
    形态 (asynccontextmanager 再包装 + yield 转发), 协程化会炸 500。
    """
    try:
        from contextlib import asynccontextmanager

        from mcp.server.sse import SseServerTransport
    except Exception as e:  # pragma: no cover
        logger.warning(f"mcp sse sentinel: mcp unavailable (skipped): {e}")
        return

    if getattr(SseServerTransport, "_mcp_sse_sentinel_armed", False):
        return

    original_connect_sse = SseServerTransport.connect_sse

    @asynccontextmanager
    async def connect_sse_with_sentinel(self: Any, scope: Any, receive: Any, send: Any):
        closer = asyncio.create_task(
            _shutdown_closer(self), name="mcp-sse-shutdown-closer"
        )
        try:
            async with original_connect_sse(self, scope, receive, send) as streams:
                yield streams
        finally:
            closer.cancel()

    SseServerTransport.connect_sse = connect_sse_with_sentinel  # type: ignore[method-assign]
    SseServerTransport._mcp_sse_sentinel_armed = True  # type: ignore[attr-defined]
    logger.info("mcp sse sentinel armed (SseServerTransport.connect_sse wrapped)")


__all__ = ["arm_mcp_sse_sentinel"]

"""DEV-0302 R1 — SSE 停机哨兵契约测试。

排空阶段 (timeout_graceful_shutdown) 依赖流 generator 在 yield 点响应取消;
本测试锁定: request_shutdown() 置位后 /api/events 流在下一个轮询点
(≤5s keepalive 间隔) 自行终结, 不再依赖 30s 长 keepalive 醒来。
"""
from __future__ import annotations

import asyncio
import time

import pytest

from backend.core import events as core_events


@pytest.fixture(autouse=True)
def _reset_shutdown_sentinel():
    """模块级哨兵每用例后强制复位 — 防状态泄漏到他文件的同进程测试
    (全量回归曾因此红 1 例: 其他 SSE 流测试看到终结帧)。"""
    core_events._shutdown_requested = False
    yield
    core_events._shutdown_requested = False


def _make_stream(queue: asyncio.Queue):
    """直接实例化 sse_events 的内部流逻辑 (与 api/events.py 逐字同构)。"""
    from backend.api.events import _KEEPALIVE_INTERVAL_S
    from backend.core.events import is_shutdown_requested, unsubscribe

    async def event_stream():
        try:
            while True:
                if is_shutdown_requested():
                    yield 'event: server_shutdown\ndata: {"type": "server_shutdown"}\n\n'
                    return
                try:
                    data = await asyncio.wait_for(
                        queue.get(), timeout=_KEEPALIVE_INTERVAL_S,
                    )
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe(queue)

    return event_stream()


def test_shutdown_sentinel_terminates_stream():
    """request_shutdown 置位 → 流在下一个轮询点 yield server_shutdown 并 return。"""
    async def scenario():
        queue = core_events.subscribe()
        gen = _make_stream(queue)
        # 第一帧: keepalive (5s 间隔内无事件)
        frame1 = await gen.__anext__()
        assert frame1 == ": keepalive\n\n"

        t0 = time.monotonic()
        core_events.request_shutdown()
        frame2 = await gen.__anext__()
        elapsed = time.monotonic() - t0

        assert "server_shutdown" in frame2
        assert elapsed < 2, f"哨兵唤醒应立即放行 ({elapsed:.2f}s)"
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()  # return 语义
        core_events.unsubscribe(queue)

    asyncio.run(scenario())


def test_request_shutdown_wakes_all_subscribers():
    """哨兵唤醒: 等待中的 queue.get 被 server_shutdown 消息立即放行。"""
    async def scenario():
        q = core_events.subscribe()
        t0 = loop_time = asyncio.get_event_loop().time()
        core_events.request_shutdown()
        msg = await asyncio.wait_for(q.get(), timeout=2)
        assert asyncio.get_event_loop().time() - t0 < 1
        assert "server_shutdown" in msg
        core_events.unsubscribe(q)

    asyncio.run(scenario())


def test_keepalive_interval_is_p3_friendly():
    """keepalive 间隔 ≤5s (停机排空预算内至少 2 个轮询点)。"""
    from backend.api.events import _KEEPALIVE_INTERVAL_S

    assert _KEEPALIVE_INTERVAL_S <= 5


def test_sse_stream_shape_unchanged():
    """非停机路径回归: 正常事件帧格式不变 (data: {payload})。"""
    async def scenario():
        q = core_events.subscribe()
        gen = _make_stream(q)
        payload = '{"id": 1, "type": "t"}'
        q.put_nowait(payload)
        frame = await asyncio.wait_for(gen.__anext__(), timeout=3)
        assert frame == f"data: {payload}\n\n"
        core_events.unsubscribe(q)
        await gen.aclose()

    asyncio.run(scenario())

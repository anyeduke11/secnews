"""DEV-0306 R10 — MCP SSE 停机终结契约测试。

只测接缝 (closer 任务 / writer 关闭 / 哨兵唤醒), 不起完整 ASGI connect_sse
(mcp 库内部行为由上游保证)。哨兵状态 autouse 复位 (防跨文件泄漏, 同
test_sse_shutdown 教训)。
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import anyio
import pytest

from backend.core import events as core_events
from backend.utils import mcp_sse_shutdown as mss


@pytest.fixture(autouse=True)
def _reset_shutdown_sentinel():
    core_events._shutdown_requested = False
    yield
    core_events._shutdown_requested = False


def _make_transport():
    """真 anyio memory stream 充当 session writer 注册表。"""
    send_stream, recv_stream = anyio.create_memory_object_stream[object](0)
    sid = uuid.uuid4()
    transport = SimpleNamespace(_read_stream_writers={sid: send_stream})
    return transport, send_stream, recv_stream


def test_close_session_writers_closes_all():
    """aclose 后 writer.send 抛 ClosedResourceError (reader 侧 async for 终结)。"""
    async def scenario():
        transport, send_stream, recv_stream = _make_transport()
        await mss._close_session_writers(transport)
        with pytest.raises(anyio.ClosedResourceError):
            await send_stream.send(object())
        await recv_stream.aclose()

    anyio.run(scenario)


def test_close_session_writers_tolerates_empty_or_broken():
    """空注册表/坏 writer 不抛 (never-fail)。"""
    async def scenario():
        await mss._close_session_writers(SimpleNamespace(_read_stream_writers={}))
        await mss._close_session_writers(SimpleNamespace())  # 无属性也不抛
        bad = SimpleNamespace(_read_stream_writers={"x": object()})  # 无 aclose
        await mss._close_session_writers(bad)

    anyio.run(scenario)


def test_shutdown_closer_wakes_on_broadcast():
    """request_shutdown 广播 → closer 关闭全部 writer → 任务自然结束。"""
    async def scenario():
        transport, send_stream, _ = _make_transport()
        task = asyncio.create_task(mss._shutdown_closer(transport))
        await asyncio.sleep(0.05)  # closer 已 subscribe
        core_events.request_shutdown()
        await asyncio.wait_for(task, timeout=2)
        with pytest.raises(anyio.ClosedResourceError):
            await send_stream.send(object())

    asyncio.run(scenario())


def test_shutdown_closer_terminates_immediately_if_already_flagged():
    """哨兵先于连接置位 (lifespan 排空期新连接) → closer 立即关 writer 返回。"""
    async def scenario():
        core_events.request_shutdown()
        transport, send_stream, _ = _make_transport()
        await asyncio.wait_for(mss._shutdown_closer(transport), timeout=1)
        with pytest.raises(anyio.ClosedResourceError):
            await send_stream.send(object())

    asyncio.run(scenario())


def test_shutdown_closer_ignores_normal_events():
    """普通事件消息不终结流 (只有 server_shutdown 触发关闭)。"""
    async def scenario():
        transport, send_stream, _ = _make_transport()
        task = asyncio.create_task(mss._shutdown_closer(transport))
        await asyncio.sleep(0.05)
        await core_events.publish_event("heartbeat", {})
        await asyncio.sleep(0.05)
        assert not task.done(), "普通事件不应终结 closer"
        core_events.request_shutdown()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(scenario())


def test_arm_is_idempotent(monkeypatch):
    from mcp.server.sse import SseServerTransport

    monkeypatch.setattr(
        SseServerTransport, "_mcp_sse_sentinel_armed", False, raising=False
    )
    mss.arm_mcp_sse_sentinel()
    first = SseServerTransport.connect_sse
    mss.arm_mcp_sse_sentinel()
    assert SseServerTransport.connect_sse is first  # 第二次不重复包装
    monkeypatch.setattr(
        SseServerTransport, "_mcp_sse_sentinel_armed", False, raising=False
    )


def test_arm_preserves_async_context_manager_shape(monkeypatch):
    """包装后 connect_sse(...) 必须仍返回 async CM (含 __aenter__/__aexit__)。

    fastapi-mcp 以 ``async with transport.connect_sse(scope, receive, send)
    as (reader, writer)`` 消费 (fastapi_mcp/server.py L197); 协程化包装
    曾致 GET /mcp/sse 生产 500 (DEV-0306 实弹) — 本用例锁死形态契约。
    """
    from mcp.server.sse import SseServerTransport

    monkeypatch.setattr(
        SseServerTransport, "_mcp_sse_sentinel_armed", False, raising=False
    )
    mss.arm_mcp_sse_sentinel()
    transport = SseServerTransport("/messages/")
    obj = transport.connect_sse({}, None, None)
    assert not asyncio.iscoroutine(obj), "协程对象会让 async with 炸"
    assert hasattr(obj, "__aenter__") and hasattr(obj, "__aexit__")
    monkeypatch.setattr(
        SseServerTransport, "_mcp_sse_sentinel_armed", False, raising=False
    )

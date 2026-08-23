"""v0.5 M2-Task5: SSE 三事件契约测试 (extract_done / job_done / task_done)。

验证 publish_event() 能正常广播, payload 形状符合 SPEC §6.2。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.api import events


@pytest.fixture(autouse=True)
def reset_subscribers():
    """每个测试前清空 _subscribers (避免上一个测试的订阅残留)。"""
    events._subscribers.clear()
    yield
    events._subscribers.clear()


@pytest.mark.asyncio
async def test_publish_event_broadcasts_to_subscribers():
    """publish_event 推送到所有订阅者。"""
    queue1: asyncio.Queue = asyncio.Queue(maxsize=10)
    queue2: asyncio.Queue = asyncio.Queue(maxsize=10)
    events._subscribers.append(queue1)
    events._subscribers.append(queue2)

    await events.publish_event("extract_done", {
        "item_id": "h-1",
        "tags": ["a", "b"],
        "lifecycle": None,
    })

    msg1 = await queue1.get()
    msg2 = await queue2.get()

    payload1 = json.loads(msg1)
    payload2 = json.loads(msg2)

    assert payload1["type"] == "extract_done"
    assert payload1["data"]["item_id"] == "h-1"
    assert payload1["data"]["tags"] == ["a", "b"]
    assert "ts" in payload1  # ISO 时间戳

    assert payload2 == payload1


@pytest.mark.asyncio
async def test_extract_done_payload_shape():
    """extract_done payload 形状: {item_id, tags:[], lifecycle} (SPEC §6.2)。"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    events._subscribers.append(queue)

    await events.publish_event("extract_done", {
        "item_id": "k-ext-1",
        "tags": ["security", "ai"],
        "lifecycle": "kl:refine",
    })
    msg = json.loads(await queue.get())
    assert msg["type"] == "extract_done"
    for k in ("item_id", "tags", "lifecycle"):
        assert k in msg["data"], f"extract_done payload 缺字段 {k}"
    assert isinstance(msg["data"]["tags"], list)


@pytest.mark.asyncio
async def test_job_done_payload_shape():
    """job_done payload 形状: {type, id, duration_ms, ok} (SPEC §6.2)。"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    events._subscribers.append(queue)

    await events.publish_event("job_done", {
        "type": "db_diet",
        "id": "db_diet-1787321478",
        "duration_ms": 540,
        "ok": True,
    })
    msg = json.loads(await queue.get())
    assert msg["type"] == "job_done"
    for k in ("type", "id", "duration_ms", "ok"):
        assert k in msg["data"]
    assert isinstance(msg["data"]["ok"], bool)


@pytest.mark.asyncio
async def test_task_done_payload_shape():
    """task_done payload 形状: {task_id, action, result} (SPEC §6.2)。"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    events._subscribers.append(queue)

    await events.publish_event("task_done", {
        "task_id": 1980,
        "action": "compile",
        "result": {"items": 5, "classified": 5, "lifecycle_advanced": 3},
    })
    msg = json.loads(await queue.get())
    assert msg["type"] == "task_done"
    for k in ("task_id", "action", "result"):
        assert k in msg["data"]


@pytest.mark.asyncio
async def test_publish_event_isolates_full_queue():
    """订阅者队列满时不应阻塞 publisher (dead queue 被剔除)。"""
    queue_full: asyncio.Queue = asyncio.Queue(maxsize=1)
    queue_alive: asyncio.Queue = asyncio.Queue(maxsize=10)
    events._subscribers.append(queue_full)
    events._subscribers.append(queue_alive)

    # 第一次填满 queue_full
    await events.publish_event("test_event", {"x": 1})
    # 第二次 queue_full 已满, 应剔除它并仅推给 queue_alive
    await events.publish_event("test_event", {"x": 2})

    # queue_alive 应收到 2 条
    msg1 = json.loads(await queue_alive.get())
    msg2 = json.loads(await queue_alive.get())
    assert msg1["data"]["x"] == 1
    assert msg2["data"]["x"] == 2

    # queue_full 已被剔除 (不应再在 _subscribers)
    assert queue_full not in events._subscribers
    assert queue_alive in events._subscribers


@pytest.mark.asyncio
async def test_legacy_events_still_publishable():
    """已有事件 (collect_done / alert / review_due) 不应破坏, payload 兼容。"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=10)
    events._subscribers.append(queue)

    for ev_type in ("collect_done", "alert", "review_due"):
        await events.publish_event(ev_type, {"category": "bid", "count": 5})
        msg = json.loads(await queue.get())
        assert msg["type"] == ev_type


def test_instrument_job_decorator_exists():
    """jobs.py 必须有 instrument_job 装饰器 (供 M2-Task5 job_done 事件用)。"""
    from backend.scheduler import jobs
    assert hasattr(jobs, "instrument_job"), "jobs.instrument_job 缺失"
    assert callable(jobs.instrument_job)


def test_job_done_event_helper():
    """jobs.job_done_event 是同步 fire-and-forget 工具。"""
    from backend.scheduler import jobs
    assert hasattr(jobs, "job_done_event")
    assert callable(jobs.job_done_event)
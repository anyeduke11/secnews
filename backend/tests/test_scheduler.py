"""HotspotScheduler 单元测试

覆盖：
  - attach_service 之前调 start() 抛 RuntimeError
  - start() + stop() 生命周期不报错
  - reschedule() 改 interval
  - 初始触发在 5s 延迟之后（用 monkeypatch 把 sleep 改成 0 加速测试）
  - attach_service / stop 同步更新 jobs._service

实现说明
--------
``AsyncIOScheduler.start()`` 内部调用 ``asyncio.get_running_loop()``，
必须在 running event loop 内执行。因此凡是真正 ``start()`` 调度器的
测试都用 ``@pytest.mark.asyncio``。
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from backend.scheduler.scheduler import HotspotScheduler


# ---------------------------------------------------------------------------
# 1. attach_service 之前调 start() 抛 RuntimeError
# ---------------------------------------------------------------------------
def test_scheduler_attach_required():
    """未 attach_service 直接 start() 应抛 RuntimeError。"""
    s = HotspotScheduler()
    with pytest.raises(RuntimeError):
        s.start()


# ---------------------------------------------------------------------------
# 2. start() + stop() 生命周期
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scheduler_start_stop():
    """attach 后 start() 设置 scheduler 字段，stop() 清空。"""
    s = HotspotScheduler()
    mock_service = AsyncMock()
    s.attach_service(mock_service)

    s.start()
    try:
        assert s.scheduler is not None
    finally:
        s.stop()
    assert s.scheduler is None


@pytest.mark.asyncio
async def test_scheduler_start_idempotent():
    """连续两次 start() 第二次应直接返回（不重置）。"""
    s = HotspotScheduler()
    mock_service = AsyncMock()
    s.attach_service(mock_service)

    s.start()
    try:
        first_scheduler = s.scheduler
        s.start()  # 第二次应 no-op
        assert s.scheduler is first_scheduler
    finally:
        s.stop()


def test_scheduler_stop_when_not_started():
    """未 start() 直接 stop() 应 no-op 不报错。"""
    s = HotspotScheduler()
    s.stop()  # 不应抛异常
    assert s.scheduler is None


# ---------------------------------------------------------------------------
# 3. reschedule 改 interval
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scheduler_reschedule_changes_interval():
    """reschedule() 应更新内部 interval 并调度到 APScheduler。"""
    s = HotspotScheduler()
    mock_service = AsyncMock()
    s.attach_service(mock_service)
    s.start()

    try:
        s.reschedule(interval_seconds=60)
        # 内部 _interval 字段已更新
        assert s._interval == 60
        # APScheduler 内部 job 的 trigger interval 也应是 60
        job = s.scheduler.get_job("collect_all")
        assert job is not None
        # trigger.interval 是 timedelta
        assert job.trigger.interval.total_seconds() == 60
    finally:
        s.stop()


def test_scheduler_reschedule_before_start():
    """未 start() 时 reschedule 仅更新内部 _interval 字段。"""
    s = HotspotScheduler()
    s.reschedule(interval_seconds=120)
    assert s._interval == 120
    assert s.scheduler is None  # 没启动仍 None


# ---------------------------------------------------------------------------
# 4. 初始触发在延迟之后
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scheduler_initial_trigger_delayed(monkeypatch):
    """``_run_initial`` 应先 ``await asyncio.sleep(5)`` 再调 ``collect_all_job``。

    monkeypatch ``asyncio.sleep`` 跳过等待，直接调用 ``_run_initial`` 验证
    调用顺序。这样可以避开 ``start()`` 中 ``asyncio.get_event_loop()``
    的 deprecated 行为，使测试可重现。
    """
    s = HotspotScheduler()
    mock_service = AsyncMock()
    s.attach_service(mock_service)

    # 记录 sleep 实际被调用了几次 / 多久
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        return None  # 立即返回

    import backend.scheduler.scheduler as scheduler_mod
    monkeypatch.setattr(scheduler_mod.asyncio, "sleep", fake_sleep)

    # 跟踪 jobs.collect_all_job 的调用次数
    call_count = 0

    async def fake_collect_all_job() -> None:
        nonlocal call_count
        call_count += 1

    import backend.scheduler.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "collect_all_job", fake_collect_all_job)

    # 直接调用 _run_initial，验证其内部行为
    await s._run_initial()

    # fake_collect_all_job 应被调用 1 次
    assert call_count == 1
    # sleep 应至少有一次是 5s
    assert any(seconds == 5 for seconds in sleep_calls)
    # 顺序：sleep(5) 必须发生在 collect_all_job 之前
    assert sleep_calls[0] == 5


@pytest.mark.asyncio
async def test_scheduler_start_schedules_initial_task(monkeypatch):
    """``start()`` 应创建一个 _run_initial 任务（无需等待它完成）。"""
    s = HotspotScheduler()
    mock_service = AsyncMock()
    s.attach_service(mock_service)

    # 跟踪任务创建
    initial_called = False
    original_run_initial = s._run_initial

    async def fake_run_initial() -> None:
        nonlocal initial_called
        initial_called = True

    monkeypatch.setattr(s, "_run_initial", fake_run_initial)

    s.start()
    try:
        # 给事件循环一点时间跑任务
        import asyncio as _aio
        for _ in range(20):
            if initial_called:
                break
            await _aio.sleep(0.01)
        # _run_initial 已被触发
        assert initial_called
    finally:
        s.stop()


# ---------------------------------------------------------------------------
# 5. attach_service 同时把 service 注入到 jobs 模块
# ---------------------------------------------------------------------------
def test_attach_service_injects_into_jobs():
    """attach_service() 应同时设置 jobs._service 供 jobs 模块使用。"""
    s = HotspotScheduler()
    mock_service = AsyncMock()
    s.attach_service(mock_service)

    from backend.scheduler import jobs as jobs_mod
    assert jobs_mod._service is mock_service

    s.stop()  # stop() 会 reset_service


@pytest.mark.asyncio
async def test_stop_resets_jobs_service():
    """stop() 后 jobs._service 应被重置为 None。"""
    s = HotspotScheduler()
    mock_service = AsyncMock()
    s.attach_service(mock_service)
    s.start()
    s.stop()

    from backend.scheduler import jobs as jobs_mod
    assert jobs_mod._service is None

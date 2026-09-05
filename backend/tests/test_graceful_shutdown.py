"""v0.8.1 Day 0 — graceful shutdown 单元测试 (V0.8.1_PRD v1.0 D-b)。

覆盖 PRD 验收的单元层: drain 三态 (0s 跳过 / 有在跑 / 无在跑 / 无法内省兜底 /
永不抛) + wal_checkpoint (truncate / 幂等 / 错误吞噬)。SIGTERM 端到端
(重启 N 次无损坏) 属 soak 层, 走 scripts/soaktest 手动验证。
"""

from __future__ import annotations

import asyncio
import sqlite3

from backend.utils import shutdown as shutdown_mod
from backend.utils.shutdown import (
    DEFAULT_GRACE_SECONDS,
    drain_in_flight,
    get_graceful_timeout,
    wal_checkpoint,
)


# ---------------------------------------------------------------------------
# 环境变量解析
# ---------------------------------------------------------------------------
class TestGracefulTimeout:
    def test_default_is_30s(self, monkeypatch):
        monkeypatch.delenv("HOTSPOT_GRACEFUL_TIMEOUT", raising=False)
        assert get_graceful_timeout() == DEFAULT_GRACE_SECONDS == 30.0

    def test_env_override_positive_and_zero(self, monkeypatch):
        monkeypatch.setenv("HOTSPOT_GRACEFUL_TIMEOUT", "5")
        assert get_graceful_timeout() == 5.0
        monkeypatch.setenv("HOTSPOT_GRACEFUL_TIMEOUT", "0")
        assert get_graceful_timeout() == 0.0

    def test_env_invalid_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("HOTSPOT_GRACEFUL_TIMEOUT", "abc")
        assert get_graceful_timeout() == DEFAULT_GRACE_SECONDS

    def test_env_negative_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv("HOTSPOT_GRACEFUL_TIMEOUT", "-3")
        assert get_graceful_timeout() == 0.0


# ---------------------------------------------------------------------------
# drain_in_flight
# ---------------------------------------------------------------------------
class _FakeExecutor:
    def __init__(self, futures=()):
        self._pending_futures = set(futures)


class _FakeApscheduler:
    def __init__(self, executors=None):
        self._executors = executors or {}


class _FakeHotspotScheduler:
    def __init__(self, apscheduler=None):
        self.scheduler = apscheduler


class TestDrainInFlight:
    def test_zero_timeout_skips_wait(self):
        stats = asyncio.run(drain_in_flight(_FakeHotspotScheduler(), timeout=0))
        assert stats["timeout_s"] == 0.0
        assert stats["waited_s"] == 0.0

    def test_none_scheduler_skips(self):
        stats = asyncio.run(drain_in_flight(None, timeout=5))
        assert stats["waited_s"] == 0.0  # 无调度器 → 不空等

    def test_waits_running_future(self):
        async def scenario():
            loop = asyncio.get_running_loop()
            fut = loop.create_task(asyncio.sleep(0.05))
            sched = _FakeHotspotScheduler(
                _FakeApscheduler({"default": _FakeExecutor([fut])})
            )
            return await drain_in_flight(sched, timeout=5)

        stats = asyncio.run(scenario())
        assert stats["introspected"] is True
        assert stats["drained"] == 1
        assert stats["left_running"] == 0
        assert stats["waited_s"] < 5

    def test_timeout_leaves_running(self):
        async def scenario():
            loop = asyncio.get_running_loop()
            fut = loop.create_task(asyncio.sleep(5))
            sched = _FakeHotspotScheduler(
                _FakeApscheduler({"default": _FakeExecutor([fut])})
            )
            stats = await drain_in_flight(sched, timeout=0.1)
            return stats, fut

        stats, fut = asyncio.run(scenario())
        assert stats["left_running"] == 1
        fut.cancel()  # 清理, 防 asyncio 残留任务警告

    def test_no_pending_no_idle_wait(self):
        """内省成功且无在跑 job → 立即返回, 不空等 timeout。"""

        async def scenario():
            sched = _FakeHotspotScheduler(_FakeApscheduler({"default": _FakeExecutor()}))
            return await drain_in_flight(sched, timeout=5)

        stats = asyncio.run(scenario())
        assert stats["introspected"] is True
        assert stats["waited_s"] < 1

    def test_no_introspection_falls_back_to_fixed_sleep(self):
        async def scenario():
            sched = _FakeHotspotScheduler(object())  # 无 _executors → 内省不可用
            return await drain_in_flight(sched, timeout=0.1)

        stats = asyncio.run(scenario())
        assert stats["introspected"] is False
        assert 0.05 <= stats["waited_s"] <= 2

    def test_never_raises_on_broken_scheduler(self):
        class _Broken:
            @property
            def scheduler(self):
                raise RuntimeError("boom")

        stats = asyncio.run(drain_in_flight(_Broken(), timeout=0.05))
        assert stats["introspected"] is False
        assert stats["waited_s"] >= 0.05  # 走固定等待兜底而非抛异常


# ---------------------------------------------------------------------------
# wal_checkpoint
# ---------------------------------------------------------------------------
class TestWalCheckpoint:
    def test_truncates_and_integrity_ok(self, temp_db):
        conn = shutdown_mod.repo_db.get_connection()
        conn.execute("CREATE TABLE IF NOT EXISTS _day0_probe (x INTEGER)")
        conn.execute("INSERT INTO _day0_probe VALUES (1)")
        conn.commit()

        assert wal_checkpoint() is True

        row = conn.execute("PRAGMA integrity_check").fetchone()
        assert row[0] == "ok"

    def test_idempotent_and_bool(self, temp_db):
        first = wal_checkpoint()
        second = wal_checkpoint()
        assert isinstance(first, bool) and isinstance(second, bool)
        assert first is True and second is True  # 空 WAL 再 checkpoint 仍成功

    def test_swallows_get_connection_error(self, monkeypatch):
        def _boom():
            raise RuntimeError("no db here")

        monkeypatch.setattr(shutdown_mod.repo_db, "get_connection", _boom)
        assert wal_checkpoint() is False

    def test_swallows_sqlite_error(self, monkeypatch):
        class _BrokenConn:
            def execute(self, *args, **kwargs):
                raise sqlite3.OperationalError("boom")

        monkeypatch.setattr(shutdown_mod.repo_db, "get_connection", lambda: _BrokenConn())
        assert wal_checkpoint() is False

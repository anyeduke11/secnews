"""v0.8.1 Day 1 — CircuitBreaker 薄状态机单元测试 (PRD §2.2 / PLAN §2.3 D1)。

注入假时钟 → 三态迁移全部确定性推进, 零 sleep; 并发用真线程 + Barrier。
trip/reset 的**驱动方**是 ProviderHealth (Day 2), 本文件只测状态机本体。
"""

from __future__ import annotations

import threading

import pytest

from backend.utils.circuit_breaker import CircuitBreaker


class _FakeClock:
    """确定性时钟 — advance 手动推时间, 测试零 sleep。"""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _make(recovery_timeout: float = 30.0) -> tuple[CircuitBreaker, _FakeClock]:
    clock = _FakeClock()
    return CircuitBreaker(recovery_timeout=recovery_timeout, clock=clock), clock


class TestStates:
    def test_initial_state_closed_and_allows(self):
        cb, _ = _make()
        assert cb.state == "closed"
        assert cb.allow() is True

    def test_trip_opens_and_rejects(self):
        cb, _ = _make()
        cb.trip()
        assert cb.state == "open"
        assert cb.allow() is False

    def test_open_expires_grants_single_probe(self):
        cb, clock = _make()
        cb.trip()
        clock.advance(30)  # 恰好到期 (>=)
        assert cb.allow() is True  # 本次调用即探针
        assert cb.state == "half_open"
        assert cb.allow() is False  # 探针在途, 第二次拒绝

    def test_reset_from_half_open_returns_closed(self):
        cb, clock = _make()
        cb.trip()
        clock.advance(30)
        assert cb.allow() is True  # 探针
        cb.reset()  # 探针成功
        assert cb.state == "closed"
        assert cb.allow() is True

    def test_probe_failure_retrips_with_new_window(self):
        cb, clock = _make()
        cb.trip()
        clock.advance(30)
        assert cb.allow() is True  # 探针 1
        clock.advance(5)
        cb.trip()  # 探针失败 → 重回 open, 重新计时
        assert cb.state == "open"
        assert cb.allow() is False  # 新窗口内拒绝
        clock.advance(29)
        assert cb.allow() is False  # 距新 opened_at 仅 29s
        clock.advance(1)
        assert cb.allow() is True  # 新窗口到期 → 探针 2

    def test_trip_while_open_is_noop_keeps_window(self):
        cb, clock = _make()
        cb.trip()
        opened_at = cb.snapshot()["opened_at"]
        clock.advance(10)
        cb.trip()  # 已 OPEN → 不延长窗口
        assert cb.snapshot()["opened_at"] == opened_at
        assert cb.state == "open"

    def test_half_open_stale_probe_regranted_no_deadlock(self):
        """探针方失联 (既不 reset 也不 trip) → 滞留超时后允许重新授予。"""
        cb, clock = _make()
        cb.trip()
        clock.advance(30)
        assert cb.allow() is True  # 探针 1 授予, 此后调用方失联
        clock.advance(30)  # half_open 滞留 ≥ recovery_timeout
        assert cb.allow() is True  # 重新授予新探针 (防死锁)
        assert cb.snapshot()["probe_granted_at"] == clock.t

    def test_reset_idempotent_on_closed(self):
        cb, _ = _make()
        cb.reset()
        cb.reset()
        assert cb.state == "closed"
        assert cb.allow() is True

    def test_zero_timeout_probes_every_call(self):
        """recovery_timeout=0: open 立即到期 + half_open 立即超时 → 每次都放探针。"""
        cb, clock = _make(recovery_timeout=0)
        cb.trip()
        assert cb.allow() is True
        assert cb.allow() is True  # half_open 滞留 0 ≥ 0 → 再授予
        assert clock.t >= 1000

    def test_custom_recovery_timeout(self):
        cb, clock = _make(recovery_timeout=7)
        assert cb.recovery_timeout == 7
        cb.trip()
        clock.advance(6.9)
        assert cb.allow() is False
        clock.advance(0.1)
        assert cb.allow() is True

    def test_negative_timeout_raises(self):
        with pytest.raises(ValueError):
            CircuitBreaker(recovery_timeout=-1)

    def test_snapshot_fields(self):
        cb, clock = _make(recovery_timeout=12)
        snap = cb.snapshot()
        assert snap == {
            "state": "closed",
            "opened_at": 0.0,
            "probe_granted_at": 0.0,
            "recovery_timeout": 12,
        }
        cb.trip()
        snap = cb.snapshot()
        assert snap["state"] == "open"
        assert snap["opened_at"] == clock.t


class TestConcurrency:
    def test_expiry_grants_exactly_one_probe(self):
        """N 线程同时 allow(): OPEN 到期后恰好 1 个获得探针, 其余拒绝。"""
        cb, clock = _make(recovery_timeout=30)
        cb.trip()
        clock.advance(30)  # 到期; 之后不再推时间 → 唯一探针窗口

        barrier = threading.Barrier(16)
        results: list[bool] = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            ok = cb.allow()
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sum(results) == 1
        assert cb.state == "half_open"

    def test_mixed_ops_keep_state_valid(self):
        """并发 trip/reset/allow 混跑: 状态恒合法、无异常、最终可继续工作。"""
        cb, clock = _make(recovery_timeout=0.01)
        errors: list[Exception] = []

        def worker(i: int):
            try:
                for j in range(50):
                    cb.allow()
                    if (i + j) % 3 == 0:
                        cb.trip()
                    elif (i + j) % 3 == 1:
                        cb.reset()
                    clock.advance(0.001)
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert cb.state in ("closed", "open", "half_open")
        cb.reset()
        assert cb.allow() is True  # 混跑后仍可正常工作

"""v0.8.1 Day 2 — ProviderHealth 唯一判定源单元测试 (PRD §2.2 / PLAN §2.3 D2)。

注入假时钟 → 窗口滚动/淘汰/阈值边界全部确定性; 并发用真线程。
breaker 驱动语义: 判定不健康 → trip; 探针失败 → 立即 trip (PRD F3);
探针成功 → reset; 窗口自行恢复不自动闭合 (恢复必须经探针)。
"""

from __future__ import annotations

import os
import threading

import pytest

from backend.services.ai_hub.provider_health import (
    DEFAULT_FAILURE_THRESHOLD,
    DEFAULT_MIN_SAMPLES,
    DEFAULT_RECOVERY_TIMEOUT,
    ProviderHealth,
    get_provider_health,
    reset_provider_health,
)


class _FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _make(**kwargs) -> tuple[ProviderHealth, _FakeClock]:
    clock = _FakeClock()
    return ProviderHealth(clock=clock, **kwargs), clock


class TestVerdict:
    def test_no_samples_not_unhealthy(self):
        ph, _ = _make()
        assert ph.is_unhealthy("sensenova") is False

    def test_below_min_samples_not_unhealthy(self):
        """min_samples=4: 3 连失败 = 100% 失败率但样本不足 → 不判死 (防单发误熔断)。"""
        ph, _ = _make()
        for _ in range(3):
            ph.record("sensenova", ok=False)
        assert ph.is_unhealthy("sensenova") is False

    def test_exactly_threshold_not_unhealthy(self):
        """4 样本 2 失败 = 50%, 阈值语义为严格 > → 不判死。"""
        ph, _ = _make()
        ph.record("sensenova", ok=False)
        ph.record("sensenova", ok=False)
        ph.record("sensenova", ok=True)
        ph.record("sensenova", ok=True)
        assert ph.is_unhealthy("sensenova") is False

    def test_above_threshold_unhealthy(self):
        ph, _ = _make()
        for ok in (False, False, False, True):
            ph.record("sensenova", ok=ok)
        assert ph.is_unhealthy("sensenova") is True

    def test_window_rolls_old_failures_expire(self):
        """5min 判定窗: 旧失败滚出后仅凭新样本判定 → 恢复。"""
        ph, clock = _make()
        for _ in range(4):
            ph.record("sensenova", ok=False)
        assert ph.is_unhealthy("sensenova") is True
        clock.advance(301)
        for _ in range(4):
            ph.record("sensenova", ok=True)
        assert ph.is_unhealthy("sensenova") is False

    def test_one_hour_eviction(self):
        """超过 1h 的样本逐出 — snapshot 1h 段归零 (内存有界)。"""
        ph, clock = _make()
        ph.record("sensenova", ok=False)
        clock.advance(3601)
        snap = ph.snapshot("sensenova")
        assert snap["windows"]["60m"]["total"] == 0

    def test_per_provider_isolation(self):
        ph, _ = _make()
        for _ in range(4):
            ph.record("sensenova", ok=False)
        for _ in range(4):
            ph.record("ollama", ok=True)
        assert ph.is_unhealthy("sensenova") is True
        assert ph.is_unhealthy("ollama") is False


class TestBreakerDriving:
    def test_verdict_trips_breaker(self):
        ph, _ = _make()
        for _ in range(4):
            ph.record("sensenova", ok=False)
        breaker = ph.get_breaker("sensenova")
        assert breaker.state == "open"  # 判定 → 自动 trip

    def test_probe_success_resets_half_open(self):
        ph, clock = _make()
        for _ in range(4):
            ph.record("sensenova", ok=False)
        breaker = ph.get_breaker("sensenova")
        clock.advance(30)  # OPEN 到期
        assert breaker.allow() is True  # 探针授予 (half_open)
        assert breaker.state == "half_open"
        ph.record("sensenova", ok=True)  # 探针成功
        assert breaker.state == "closed"

    def test_probe_failure_retrips_without_window(self):
        """探针失败立即重回 OPEN — 不等 5min 窗口 (样本不足时窗口判不死)。"""
        ph, clock = _make()
        for _ in range(4):
            ph.record("sensenova", ok=False)
        breaker = ph.get_breaker("sensenova")
        clock.advance(30)
        assert breaker.allow() is True  # 探针
        assert breaker.state == "half_open"
        ph.record("sensenova", ok=False)  # 探针失败 (此时 5min 窗内 5 失败, 判定也死)
        assert breaker.state == "open"

    def test_probe_failure_min_samples_edge(self):
        """探针失败 + 窗口样本不足 → 仍立即 trip (探针结果即判定, PRD F3)。"""
        ph, clock = _make()
        breaker = ph.get_breaker("sensenova")
        breaker.trip()
        clock.advance(30)
        assert breaker.allow() is True  # 探针 (half_open)
        ph.record("sensenova", ok=False)  # 唯一样本, 判定不死, 但探针失败
        assert breaker.state == "open"

    def test_window_recovery_does_not_auto_close_breaker(self):
        """窗口自行恢复不自动闭合 breaker — 恢复必须经探针 (PRD F3)。"""
        ph, clock = _make()
        for _ in range(4):
            ph.record("sensenova", ok=False)
        breaker = ph.get_breaker("sensenova")
        assert breaker.state == "open"
        clock.advance(400)  # 5min 判定窗 + 部分保留窗全滚走
        for _ in range(4):
            ph.record("sensenova", ok=True)
        assert ph.is_unhealthy("sensenova") is False
        assert breaker.state == "open"  # 仍 OPEN, 等探针

    def test_breaker_reused_per_provider(self):
        ph, _ = _make()
        b1 = ph.get_breaker("sensenova")
        b2 = ph.get_breaker("sensenova")
        assert b1 is b2

    def test_providers_have_independent_breakers(self):
        ph, _ = _make()
        b1 = ph.get_breaker("sensenova")
        b2 = ph.get_breaker("ollama")
        assert b1 is not b2


class TestSnapshot:
    def test_snapshot_structure(self):
        ph, _ = _make()
        for ok in (False, True):
            ph.record("sensenova", ok=ok)
        snap = ph.snapshot("sensenova")
        assert snap["provider"] == "sensenova"
        assert set(snap["windows"].keys()) == {"1m", "5m", "60m"}
        assert snap["windows"]["1m"]["total"] == 2
        assert snap["windows"]["1m"]["failures"] == 1
        assert snap["windows"]["1m"]["failure_rate"] == 0.5
        assert "unhealthy" in snap and "breaker" in snap
        assert snap["breaker"]["state"] == "closed"

    def test_snapshot_all(self):
        ph, _ = _make()
        ph.record("sensenova", ok=True)
        ph.record("ollama", ok=True)
        assert set(ph.snapshot_all().keys()) == {"sensenova", "ollama"}


class TestConcurrency:
    def test_concurrent_records_no_loss(self):
        """8 线程 × 50 record 同 provider → 窗口总数恰 400 (锁无丢账)。"""
        ph, _ = _make(min_samples=10**9)  # 判定永不触发, 纯测记账
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            for _ in range(50):
                ph.record("sensenova", ok=False)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        snap = ph.snapshot("sensenova")
        assert snap["windows"]["60m"]["total"] == 400


class TestSingletonAndEnv:
    def setup_method(self):
        reset_provider_health()
        self._saved = {
            k: k for k in os.environ if k.startswith("HOTSPOT_BREAKER_")
        }

    def teardown_method(self):
        reset_provider_health()

    def test_singleton_identity(self):
        assert get_provider_health() is get_provider_health()
        reset_provider_health()
        assert get_provider_health() is not None

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("HOTSPOT_BREAKER_FAILURE_THRESHOLD", "0.8")
        monkeypatch.setenv("HOTSPOT_BREAKER_MIN_SAMPLES", "2")
        monkeypatch.setenv("HOTSPOT_BREAKER_RECOVERY_TIMEOUT", "15")
        ph = get_provider_health()
        assert ph._failure_threshold == 0.8
        assert ph._min_samples == 2
        assert ph._recovery_timeout == 15

    def test_env_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("HOTSPOT_BREAKER_FAILURE_THRESHOLD", "abc")
        monkeypatch.setenv("HOTSPOT_BREAKER_MIN_SAMPLES", "-3")
        ph = get_provider_health()
        assert ph._failure_threshold == DEFAULT_FAILURE_THRESHOLD
        assert ph._min_samples == DEFAULT_MIN_SAMPLES

    def test_defaults(self):
        ph = get_provider_health()
        assert ph._failure_threshold == DEFAULT_FAILURE_THRESHOLD == 0.5
        assert ph._min_samples == DEFAULT_MIN_SAMPLES == 4
        assert ph._recovery_timeout == DEFAULT_RECOVERY_TIMEOUT == 30.0


class TestValidation:
    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            ProviderHealth(failure_threshold=1.5)

    def test_invalid_min_samples_raises(self):
        with pytest.raises(ValueError):
            ProviderHealth(min_samples=0)

"""ProviderHealth — LLM provider 健康度唯一计数/判定源 (v0.8.1 Day 2)。

V0.8.1_PRD v1.0 §2.2 / V0.8.1_PLAN v1.2 §2.2 定稿契约:

- **单一真相源** (prd-iterative 审查 P0-1): 全部失败记账与"不健康"判定都在
  此处; CircuitBreaker (Day 1) 只做薄状态机, ``trip()`` 由本模块判定驱动。
- **判定只用 5min 窗口**; 1min / 1h 仅为 /api/llm/health 展示段 (审查 P2-1)。
- **min_samples 防单发误熔断** (审查批判性补强): 样本数不足时永不判不健康 —
  否则 1 次失败 = 100% 失败率, 单发抖动即熔断 (PRD §9 风险表)。
- 进程内 deque, **不持久化** — 重启清零, 重启后最多再失败 N 次即重 OPEN
  (可接受语义, PRD §9 明示)。
- 线程安全: 单把 ``threading.Lock``; breaker 操作在锁外 (breaker 自带锁,
  判定→trip 的竞态由 trip 的 no-op 语义吸收)。
- **驱动 breaker**: ``record(fail)`` 且判定不健康 → 自动 ``trip()``;
  ``record(ok)`` 且 breaker 处于 half_open (探针成功) → ``reset()``;
  窗口自行恢复**不**自动闭合 breaker — 恢复必须经探针 (PRD F3)。

环境变量 (裁决点 D3, 演练后校准):
- ``HOTSPOT_BREAKER_FAILURE_THRESHOLD``  5min 失败率阈值, 默认 0.5 (">50%")
- ``HOTSPOT_BREAKER_MIN_SAMPLES``        判定最小样本数, 默认 4
- ``HOTSPOT_BREAKER_RECOVERY_TIMEOUT``   breaker OPEN 时长秒, 默认 30
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from collections.abc import Callable

from loguru import logger as _logger

from backend.utils.circuit_breaker import CircuitBreaker

_WINDOW_DISPLAY = (60.0, 300.0, 3600.0)  # 1min / 5min(判定) / 1min 展示段
_RETENTION_SECONDS = 3600.0  # 最长保留 1h, 之外逐出

DEFAULT_FAILURE_THRESHOLD = 0.5
DEFAULT_MIN_SAMPLES = 4
DEFAULT_RECOVERY_TIMEOUT = 30.0


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        v = float(raw)
    except ValueError:
        return default
    return v if v >= 0 else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    return v if v >= 0 else default


class ProviderHealth:
    """per-provider 滑动窗口 + 唯一"不健康"判定 + breaker 驱动。"""

    def __init__(
        self,
        failure_threshold: float = DEFAULT_FAILURE_THRESHOLD,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        recovery_timeout: float = DEFAULT_RECOVERY_TIMEOUT,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not 0 < failure_threshold <= 1:
            raise ValueError("failure_threshold 必须在 (0, 1]")
        if min_samples < 1:
            raise ValueError("min_samples 必须 >= 1")
        self._failure_threshold = float(failure_threshold)
        self._min_samples = int(min_samples)
        self._recovery_timeout = float(recovery_timeout)
        self._clock: Callable[[], float] = clock or time.monotonic
        self._lock = threading.Lock()
        # provider -> deque[(ts, ok)]；仅保留 RETENTION_SECONDS 内样本
        self._windows: dict[str, deque] = {}
        self._breakers: dict[str, CircuitBreaker] = {}

    # ------------------------------------------------------------------
    # 内部 (调用方须已持锁)
    # ------------------------------------------------------------------
    def _evict_locked(self, dq: deque, now: float) -> None:
        while dq and now - dq[0][0] > _RETENTION_SECONDS:
            dq.popleft()

    def _rate_locked(self, dq: deque, now: float, window: float) -> tuple[int, int, float]:
        total = failures = 0
        for ts, ok in reversed(dq):
            if now - ts > window:
                break  # deque 按 ts 递增, 从新到旧, 出窗即止
            total += 1
            failures += 0 if ok else 1
        rate = failures / total if total else 0.0
        return total, failures, rate

    def _unhealthy_locked(self, dq: deque, now: float) -> bool:
        total, failures, _ = self._rate_locked(dq, now, 300.0)
        if total < self._min_samples:
            return False
        return failures / total > self._failure_threshold

    def _get_breaker_locked(self, provider: str) -> CircuitBreaker:
        breaker = self._breakers.get(provider)
        if breaker is None:
            breaker = CircuitBreaker(recovery_timeout=self._recovery_timeout, clock=self._clock)
            self._breakers[provider] = breaker
        return breaker

    # ------------------------------------------------------------------
    # 公有 API
    # ------------------------------------------------------------------
    def record(self, provider: str, ok: bool) -> None:
        """记账一次 provider 调用结果, 并驱动 breaker (判定→trip / 探针成功→reset)。

        永不抛异常 — 记账失败只告警 (调用路径在 LLM 主链上, 不因观测拖垮业务)。
        """
        now = self._clock()
        breaker: CircuitBreaker | None = None
        unhealthy = False
        try:
            with self._lock:
                dq = self._windows.setdefault(provider, deque())
                dq.append((now, ok))
                self._evict_locked(dq, now)
                unhealthy = self._unhealthy_locked(dq, now)
                breaker = self._get_breaker_locked(provider)
        except Exception as exc:  # pragma: no cover - 防御性
            _logger.warning(f"provider_health record failed (ignored): {exc}")
            return
        # breaker 自带锁, 判定→trip 的竞态由 trip 的 no-op 语义吸收;
        # 最后写者赢的 reset/trip 交错由下一轮 record 再纠正。
        try:
            if breaker is None:
                return
            if not ok:
                if breaker.state == "half_open":
                    # 探针失败 → 立即重回 OPEN (PRD F3)。探针结果本身即判定,
                    # 不等 5min 窗口 — 否则窗口样本 < min_samples 时探针失败
                    # 无法 trip, breaker 卡 half_open 直到滞留超时。
                    breaker.trip()
                elif unhealthy:
                    breaker.trip()
            elif ok and breaker.state == "half_open":
                breaker.reset()  # 探针成功
        except Exception as exc:  # pragma: no cover - 防御性
            _logger.warning(f"provider_health breaker drive failed (ignored): {exc}")

    def is_unhealthy(self, provider: str) -> bool:
        """5min 窗口判定 (唯一真相源)。样本 < min_samples 恒 False。"""
        now = self._clock()
        with self._lock:
            dq = self._windows.get(provider)
            if not dq:
                return False
            return self._unhealthy_locked(dq, now)

    def get_breaker(self, provider: str) -> CircuitBreaker:
        """per-provider breaker (懒创建复用; gateway 调用前 allow() 检查用)。"""
        with self._lock:
            return self._get_breaker_locked(provider)

    def snapshot(self, provider: str) -> dict:
        """单 provider 快照 — /api/llm/health (Day 4) 输出体。"""
        now = self._clock()
        with self._lock:
            dq = self._windows.get(provider)
            windows = {}
            for w in _WINDOW_DISPLAY:
                total, failures, rate = self._rate_locked(dq, now, w) if dq else (0, 0, 0.0)
                key = f"{int(w // 60)}m"
                windows[key] = {
                    "total": total,
                    "failures": failures,
                    "failure_rate": round(rate, 4),
                }
            breaker = self._get_breaker_locked(provider)
            unhealthy = self._unhealthy_locked(dq, now) if dq else False
        return {
            "provider": provider,
            "windows": windows,
            "unhealthy": unhealthy,
            "breaker": breaker.snapshot(),
        }

    def snapshot_all(self) -> dict[str, dict]:
        """全 provider 快照 (含仅 trip 过但尚无记录的 provider 不出现)。"""
        with self._lock:
            providers = sorted(self._windows.keys())
        return {p: self.snapshot(p) for p in providers}


# ---------------------------------------------------------------------------
# 模块级单例 (对齐 trigger_webhook_api 的 wh_mod._default 可测性模式)
# ---------------------------------------------------------------------------
_default: ProviderHealth | None = None


def get_provider_health() -> ProviderHealth:
    """进程级单例 (懒创建, env 参数只读一次)。gateway/image 接入 (Day 3) 用此。"""
    global _default
    if _default is None:
        _default = ProviderHealth(
            failure_threshold=_env_float("HOTSPOT_BREAKER_FAILURE_THRESHOLD", DEFAULT_FAILURE_THRESHOLD),
            min_samples=_env_int("HOTSPOT_BREAKER_MIN_SAMPLES", DEFAULT_MIN_SAMPLES),
            recovery_timeout=_env_float("HOTSPOT_BREAKER_RECOVERY_TIMEOUT", DEFAULT_RECOVERY_TIMEOUT),
        )
    return _default


def reset_provider_health() -> None:
    """测试/运维复位单例 (下一 get 重建)。"""
    global _default
    _default = None

"""三态断路器 (薄状态机) — v0.8.1 Day 1 (V0.8.1_PRD v1.0 / V0.8.1_PLAN v1.2 §2.2)。

职责边界 (单一真相源, prd-iterative 审查 P0-1 修正):
- 本类**不持任何失败计数** — ``trip()`` 由调用方依据 ProviderHealth.is_unhealthy()
  的判定触发 (Day 2 落地), ``reset()`` 由探针成功或手动运维触发。
- keying = provider 级 (调用方持有 ``dict[provider, CircuitBreaker]``, ~5 实例);
  场景级避让交给 quality/scenario_router 权重表 (Day 4)。
- 线程安全: 单把 ``threading.Lock``, 临界区微秒级 (TriggerWorker 短线程 ×
  event loop 混跑, 仓内线程亲和教训)。

三态语义:
- ``closed``    → ``allow()=True``, 正常放行
- ``open``      → ``allow()=False``; 距 ``opened_at`` ≥ recovery_timeout 后,
  下一次 ``allow()`` 转入 half_open 并放行唯一探针
- ``half_open`` → 探针在途, ``allow()=False``; 探针成功 → ``reset()`` 回
  closed; 探针失败 → ``trip()`` 重回 open (重新计时)。half_open 滞留超过
  recovery_timeout (调用方失联) 视为探针超时, 允许重新授予新探针 — 防止
  探针方崩溃导致永久 half_open 死锁。
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Literal

BreakerState = Literal["closed", "open", "half_open"]


class CircuitBreaker:
    """薄三态状态机 — 无失败计数, trip/reset 由 ProviderHealth 判定驱动。"""

    __slots__ = (
        "_clock",
        "_lock",
        "_opened_at",
        "_probe_granted_at",
        "_recovery_timeout",
        "_state",
    )

    def __init__(
        self,
        recovery_timeout: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if recovery_timeout < 0:
            raise ValueError("recovery_timeout 必须 >= 0")
        self._recovery_timeout = float(recovery_timeout)
        # 可注入时钟 (单测免 sleep, 确定性推进); 生产用 monotonic 防系统时间回拨
        self._clock: Callable[[], float] = clock or time.monotonic
        self._lock = threading.Lock()
        self._state: BreakerState = "closed"
        self._opened_at: float = 0.0
        self._probe_granted_at: float = 0.0

    @property
    def state(self) -> BreakerState:
        with self._lock:
            return self._state

    @property
    def recovery_timeout(self) -> float:
        return self._recovery_timeout

    def allow(self) -> bool:
        """是否放行本次调用。open 到期时本调用即被授予探针 (转入 half_open)。"""
        now = self._clock()
        with self._lock:
            if self._state == "closed":
                return True
            if self._state == "open":
                if now - self._opened_at >= self._recovery_timeout:
                    self._state = "half_open"
                    self._probe_granted_at = now
                    return True  # 本次调用即探针
                return False
            # half_open: 探针在途; 滞留超时 (调用方失联) 则重新授予
            if now - self._probe_granted_at >= self._recovery_timeout:
                self._probe_granted_at = now
                return True
            return False

    def trip(self) -> None:
        """判为不健康 → OPEN。half_open 探针失败也走此 (重新计时);
        已 OPEN 时 no-op (不延长原窗口 — 窗口起点 = 首次 trip 时刻)。"""
        now = self._clock()
        with self._lock:
            if self._state == "open":
                return
            self._state = "open"
            self._opened_at = now

    def reset(self) -> None:
        """探针成功或手动复位 → CLOSED。幂等。"""
        with self._lock:
            self._state = "closed"
            self._opened_at = 0.0
            self._probe_granted_at = 0.0

    def snapshot(self) -> dict:
        """只读状态快照 — 供 /api/llm/health (Day 4) 输出。"""
        with self._lock:
            return {
                "state": self._state,
                "opened_at": self._opened_at,
                "probe_granted_at": self._probe_granted_at,
                "recovery_timeout": self._recovery_timeout,
            }

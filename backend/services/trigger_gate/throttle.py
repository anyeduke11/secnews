"""trigger-gate 限流器 — 双层令牌桶 (v0.8 Phase A).

两层桶防止两类过载:
- **per-user 桶** (默认 60/min): 单用户刷接口不至于饿死其他人
- **global 桶** (默认 600/min): 全系统总量闸门, 兜底横向聚合

令牌桶参数 (容量 = 每分钟速率, 即突发额度等于一分钟配额):
- capacity = rate (per_minute)
- refill_rate = rate / 60 (每秒补充)

超限行为: ``acquire()`` 抛 ``ThrottleExceededError`` (携带
``retry_after_seconds``, API 层后续映射 HTTP 429 + Retry-After),
调用方 (TriggerGate.submit) 不入队 — 限流拒绝与队列持久化完全解耦。

时间源可注入 (``time_fn``, 默认 ``time.monotonic``): 单测里用一个
可推进的假时钟即可验证"等待 60s 后桶恢复", 不必真 sleep。
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable


class ThrottleExceededError(Exception):
    """限流超限异常 — API 层应映射为 HTTP 429 + Retry-After。

    Attributes:
        retry_after_seconds: 补回 1 个令牌所需等待的秒数 (>= 0)。
        scope: 超限的桶标识 ("global" 或 "user:<id>"), 便于定位与观测。
    """

    def __init__(self, retry_after_seconds: float, scope: str = "global") -> None:
        self.retry_after_seconds = max(0.0, float(retry_after_seconds))
        self.scope = scope
        super().__init__(
            f"trigger throttle exceeded ({scope}), "
            f"retry after {self.retry_after_seconds:.1f}s"
        )


class _TokenBucket:
    """单只令牌桶 — 容量 = 每分钟速率, 按秒线性回填。

    非线程安全 (由外层 TriggerThrottle 的锁保护);
    时间源注入便于测试推进时钟。
    """

    def __init__(
        self,
        per_minute: int,
        time_fn: Callable[[], float],
    ) -> None:
        self.capacity = float(per_minute)
        self.tokens = float(per_minute)
        self.refill_per_second = per_minute / 60.0
        self._time_fn = time_fn
        self._last_refill = time_fn()

    def _refill(self) -> None:
        """按距上次补充的流逝时间回填令牌 (封顶 capacity)。"""
        now = self._time_fn()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
            self._last_refill = now

    def try_acquire(self) -> float:
        """尝试取 1 个令牌; 成功返回 0.0, 失败返回需等待秒数。"""
        self._refill()
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        needed = 1.0 - self.tokens
        return needed / self.refill_per_second


class TriggerThrottle:
    """双层令牌桶限流器 (per-user + global)。

    ``acquire(user_id)`` 语义: 先检查用户桶, 再检查全局桶,
    任一超限即抛 ``ThrottleExceededError``; 两桶都拿到令牌才放行。
    anonymous (user_id=None) 归并到一只共享匿名桶。
    """

    def __init__(
        self,
        per_user_per_minute: int = 60,
        global_per_minute: int = 600,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._time_fn = time_fn or time.monotonic
        self._per_user_capacity = per_user_per_minute
        self._global_bucket = _TokenBucket(global_per_minute, self._time_fn)
        self._user_buckets: dict[str, _TokenBucket] = {}
        self._lock = threading.Lock()

    def acquire(self, user_id: str | None = None) -> None:
        """消费 1 次配额; 超限抛 ThrottleExceededError (含 retry_after)。"""
        with self._lock:
            key = user_id or ""
            bucket = self._user_buckets.get(key)
            if bucket is None:
                bucket = _TokenBucket(self._per_user_capacity, self._time_fn)
                self._user_buckets[key] = bucket
            wait_user = bucket.try_acquire()
            if wait_user > 0:
                raise ThrottleExceededError(wait_user, scope=f"user:{user_id or 'anonymous'}")
            wait_global = self._global_bucket.try_acquire()
            if wait_global > 0:
                raise ThrottleExceededError(wait_global, scope="global")


__all__ = ["ThrottleExceededError", "TriggerThrottle"]

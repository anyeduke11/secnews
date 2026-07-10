"""Phase 4 缓存层 — 3 个 TTLCache 实例 + 失效 + warmup + stats。

设计
----
- ``list_cache``   列表查询（每类首页 / 趋势 / 类别列表）— TTL 5min
- ``detail_cache`` 单 item 详情（hotspot by id）— TTL 10min
- ``static_cache`` 准静态（categories / quality rules / health 简化版）— TTL 24h

缓存 key 命名约定
------------------
- ``hotspots:list:<category>:<time_range>:<cursor>:<limit>``
- ``hotspots:detail:<id>``
- ``trends:24h``
- ``categories:all``
- ``quality:summary``
- ``quality:rules``
- ``health:simple``

失效（写操作）
--------------
- 采集完成 → :func:`invalidate` ``"hotspots:*"`` + ``"trends:*"``
- 单 item 写 → ``"hotspots:detail:<id>"``
- 质量配置更新 → ``"quality:*"``

不引入新依赖，使用标准库 ``functools.lru_cache`` 的替代品 — 这里用
手写的 ``TTLCache`` 实现（避免引入 cachetools 之外的库）。
"""
from __future__ import annotations

import fnmatch
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Optional

from backend.observability import log_event


class TTLCache:
    """线程安全的 LRU+TTL 缓存。

    - ``maxsize`` 上限触发 LRU 淘汰
    - ``ttl`` 秒数过期
    - ``__getitem__`` / ``__setitem__`` 简洁 API
    - :meth:`invalidate` 模糊删除
    - :meth:`stats` 容量统计
    """

    def __init__(self, maxsize: int = 64, ttl: int = 300, name: str = ""):
        self.maxsize = maxsize
        self.ttl = ttl
        self.name = name  # observability 事件 cache_name
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()
        # metrics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.invalidations = 0

    # ------------------------------------------------------------------
    def __setitem__(self, key: str, value: Any) -> None:
        with self._lock:
            now = time.time()
            if key in self._store:
                # update
                self._store[key] = (now, value)
                self._store.move_to_end(key)
            else:
                self._store[key] = (now, value)
                if len(self._store) > self.maxsize:
                    self._store.popitem(last=False)
                    self.evictions += 1

    def __getitem__(self, key: str) -> Any:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                log_event(
                    "cache_miss",
                    cache_name=self.name,
                    key=key,
                    misses=self.misses,
                    hits=self.hits,
                )
                raise KeyError(key)
            expires_at, value = entry
            if expires_at + self.ttl < time.time():
                # expired
                del self._store[key]
                self.misses += 1
                log_event(
                    "cache_miss",
                    cache_name=self.name,
                    key=key,
                    reason="expired",
                    misses=self.misses,
                )
                raise KeyError(key)
            # warmup 哨兵：值是 ``{"_warmed": True}``，视为 miss
            if isinstance(value, dict) and value.get("_warmed") is True:
                self.misses += 1
                log_event(
                    "cache_miss",
                    cache_name=self.name,
                    key=key,
                    reason="warmed_sentinel",
                    misses=self.misses,
                )
                raise KeyError(key)
            self.hits += 1
            self._store.move_to_end(key)
            total = self.hits + self.misses
            log_event(
                "cache_hit",
                cache_name=self.name,
                key=key,
                hits=self.hits,
                misses=self.misses,
                hit_rate=round(self.hits / total, 4) if total else 0.0,
            )
            return value

    def __contains__(self, key: str) -> bool:
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key: str, default: Any = None) -> Any:
        with self._lock:
            entry = self._store.pop(key, None)
        return entry[1] if entry is not None else default

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.invalidations += self.hits + self.misses
            self.hits = self.misses = 0

    # ------------------------------------------------------------------
    def invalidate(self, pattern: str) -> int:
        """模糊删除所有匹配 ``pattern`` 的键。返回删除的条目数。"""
        with self._lock:
            keys = list(self._store.keys())
            matched = [k for k in keys if fnmatch.fnmatchcase(k, pattern)]
            for k in matched:
                del self._store[k]
            self.invalidations += len(matched)
        if matched:
            log_event(
                "cache_invalidate",
                cache_name=self.name,
                pattern=pattern,
                n_invalidated=len(matched),
            )
        return len(matched)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._store),
                "maxsize": self.maxsize,
                "ttl": self.ttl,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "invalidations": self.invalidations,
            }

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())


# ---------------------------------------------------------------------------
# 3 个实例
# ---------------------------------------------------------------------------
list_cache: TTLCache = TTLCache(maxsize=64, ttl=300, name="list")
detail_cache: TTLCache = TTLCache(maxsize=2000, ttl=600, name="detail")
static_cache: TTLCache = TTLCache(maxsize=16, ttl=86400, name="static")


# ---------------------------------------------------------------------------
# 全局失效 + warmup
# ---------------------------------------------------------------------------
def invalidate(pattern: str) -> dict[str, int]:
    """在所有 3 个 cache 上跑模糊删除。"""
    return {
        "list": list_cache.invalidate(pattern),
        "detail": detail_cache.invalidate(pattern),
        "static": static_cache.invalidate(pattern),
    }


def warmup() -> dict[str, int]:
    """启动时预热：插入"标记"条目（哨兵 = 0），避免冷启动全部走 DB。

    Returns 实际 warmup 的键数。哨兵值会在第一次真实请求时被覆盖。
    """
    warm_keys = {
        list_cache: [
            "hotspots:list:all:7d::50",
            "hotspots:list:ai:7d::50",
            "hotspots:list:security:7d::50",
            "trends:24h",
            "trends:categories",
        ],
        static_cache: [
            "categories:all",
            "health:simple",
            "quality:summary",
            "quality:rules",
        ],
        detail_cache: [],
    }
    count = 0
    for cache, keys in warm_keys.items():
        for k in keys:
            if k not in cache:
                cache[k] = {"_warmed": True}
                count += 1
    return {"warmed": count}


def stats() -> dict[str, dict[str, int]]:
    """聚合 3 个 cache 的容量信息。"""
    return {
        "list": list_cache.stats(),
        "detail": detail_cache.stats(),
        "static": static_cache.stats(),
    }


def hit_rate() -> dict[str, float]:
    """每个 cache 的命中率（hits / (hits+misses)）。"""
    out: dict[str, float] = {}
    for name, cache in (
        ("list", list_cache),
        ("detail", detail_cache),
        ("static", static_cache),
    ):
        total = cache.hits + cache.misses
        out[name] = (cache.hits / total) if total > 0 else 0.0
    return out


__all__ = [
    "TTLCache",
    "list_cache",
    "detail_cache",
    "static_cache",
    "invalidate",
    "warmup",
    "stats",
    "hit_rate",
]

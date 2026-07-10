"""TTLCache 单元测试

覆盖:
  - 基本 get/set 语义
  - TTL 过期
  - LRU 容量淘汰
  - invalidate 模糊匹配 (fnmatch)
  - 命中率 / 淘汰 / 失效 metrics
  - warmup 哨兵逻辑 (``{"_warmed": True}`` 视为 miss)
  - thread safety

不依赖任何外部资源 (DB / network)。
"""
from __future__ import annotations

import threading
import time

import pytest

from backend.cache import (
    TTLCache,
    detail_cache,
    invalidate,
    list_cache,
    static_cache,
    stats,
    warmup,
)


# ---------------------------------------------------------------------------
# 1. 基本语义
# ---------------------------------------------------------------------------
def test_set_get_basic():
    c = TTLCache(maxsize=10, ttl=60)
    c["k1"] = "v1"
    assert c["k1"] == "v1"


def test_get_missing_raises_keyerror():
    c = TTLCache(maxsize=10, ttl=60)
    with pytest.raises(KeyError):
        _ = c["missing"]


def test_get_with_default():
    c = TTLCache(maxsize=10, ttl=60)
    assert c.get("missing", "default") == "default"
    assert c.get("missing") is None


def test_len():
    c = TTLCache(maxsize=10, ttl=60)
    assert len(c) == 0
    c["a"] = 1
    c["b"] = 2
    assert len(c) == 2


def test_pop_returns_value():
    c = TTLCache(maxsize=10, ttl=60)
    c["k"] = "v"
    assert c.pop("k") == "v"
    assert c.pop("k") is None  # 不存在
    assert c.pop("missing", "fallback") == "fallback"


def test_clear_resets_metrics():
    c = TTLCache(maxsize=10, ttl=60)
    c["k"] = "v"
    _ = c["k"]
    c.clear()
    assert len(c) == 0
    # clear() 不直接重置 hits/misses（由 invalidate 路径计数）
    # 但 size 应为 0
    s = c.stats()
    assert s["size"] == 0


# ---------------------------------------------------------------------------
# 2. TTL 过期
# ---------------------------------------------------------------------------
def test_ttl_expiry():
    c = TTLCache(maxsize=10, ttl=0)  # ttl=0 → 立即过期
    c["k"] = "v"
    time.sleep(0.05)  # 让 time.time() 走过一个 tick
    with pytest.raises(KeyError):
        _ = c["k"]


def test_ttl_long_does_not_expire():
    c = TTLCache(maxsize=10, ttl=10)
    c["k"] = "v"
    assert c["k"] == "v"


def test_contains_returns_false_for_expired():
    c = TTLCache(maxsize=10, ttl=0)
    c["k"] = "v"
    time.sleep(0.05)
    assert "k" not in c


# ---------------------------------------------------------------------------
# 3. LRU 容量淘汰
# ---------------------------------------------------------------------------
def test_lru_eviction():
    c = TTLCache(maxsize=3, ttl=60)
    c["a"] = 1
    c["b"] = 2
    c["c"] = 3
    c["d"] = 4  # 触发淘汰
    assert len(c) == 3
    assert "a" not in c  # 最久未使用被淘汰
    assert "b" in c
    assert "d" in c
    s = c.stats()
    assert s["evictions"] == 1


def test_lru_get_promotes():
    c = TTLCache(maxsize=3, ttl=60)
    c["a"] = 1
    c["b"] = 2
    c["c"] = 3
    _ = c["a"]  # 提升 a 的 LRU 位置
    c["d"] = 4
    # b 是最久未使用了 → 被淘汰
    assert "b" not in c
    assert "a" in c
    assert "d" in c


# ---------------------------------------------------------------------------
# 4. invalidate 模糊匹配
# ---------------------------------------------------------------------------
def test_invalidate_exact():
    c = TTLCache(maxsize=10, ttl=60)
    c["hotspots:list:ai:7d"] = "x"
    c["hotspots:list:security:7d"] = "y"
    n = c.invalidate("hotspots:list:ai:7d")
    assert n == 1
    assert "hotspots:list:ai:7d" not in c
    assert "hotspots:list:security:7d" in c


def test_invalidate_wildcard():
    c = TTLCache(maxsize=10, ttl=60)
    c["hotspots:list:ai:7d"] = "x"
    c["hotspots:list:security:7d"] = "y"
    c["trends:24h"] = "z"
    n = c.invalidate("hotspots:*")
    assert n == 2
    assert "hotspots:list:ai:7d" not in c
    assert "hotspots:list:security:7d" not in c
    assert "trends:24h" in c


def test_invalidate_no_match():
    c = TTLCache(maxsize=10, ttl=60)
    c["k1"] = "v1"
    n = c.invalidate("nonexistent:*")
    assert n == 0


def test_invalidate_updates_metric():
    c = TTLCache(maxsize=10, ttl=60)
    c["a"] = 1
    c["b"] = 2
    c.invalidate("*")
    assert c.stats()["invalidations"] == 2


# ---------------------------------------------------------------------------
# 5. metrics
# ---------------------------------------------------------------------------
def test_hits_and_misses():
    c = TTLCache(maxsize=10, ttl=60)
    c["k"] = "v"
    _ = c["k"]  # hit
    _ = c["k"]  # hit
    with pytest.raises(KeyError):
        _ = c["missing"]  # miss
    s = c.stats()
    assert s["hits"] == 2
    assert s["misses"] == 1


def test_expired_counts_as_miss():
    c = TTLCache(maxsize=10, ttl=0)
    c["k"] = "v"
    time.sleep(0.05)
    with pytest.raises(KeyError):
        _ = c["k"]
    s = c.stats()
    assert s["misses"] == 1


# ---------------------------------------------------------------------------
# 6. warmup 哨兵
# ---------------------------------------------------------------------------
def test_warmup_sentinel_treated_as_miss():
    c = TTLCache(maxsize=10, ttl=60)
    c["k"] = {"_warmed": True}
    # __contains__ 应返回 False (因为视为 miss)
    assert "k" not in c
    with pytest.raises(KeyError):
        _ = c["k"]


def test_warmup_overwrites_with_real_value():
    c = TTLCache(maxsize=10, ttl=60)
    c["k"] = {"_warmed": True}
    c["k"] = {"data": "real"}  # 覆盖哨兵
    assert "k" in c
    assert c["k"] == {"data": "real"}


# ---------------------------------------------------------------------------
# 7. Thread safety
# ---------------------------------------------------------------------------
def test_thread_safety_basic():
    c = TTLCache(maxsize=100, ttl=60)

    def writer(start: int) -> None:
        for i in range(start, start + 50):
            c[f"k{i}"] = i

    def reader() -> None:
        for i in range(100):
            _ = c.get(f"k{i}", None)

    threads = [
        threading.Thread(target=writer, args=(0,)),
        threading.Thread(target=writer, args=(50,)),
        threading.Thread(target=reader),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 不应崩溃；len 可能为 100 或部分（取决于执行顺序）
    assert len(c) <= 100


# ---------------------------------------------------------------------------
# 8. 模块级实例 (list/detail/static) + 顶层 helpers
# ---------------------------------------------------------------------------
def test_module_level_instances_exist():
    assert list_cache.maxsize == 64
    assert list_cache.ttl == 300
    assert detail_cache.maxsize == 2000
    assert detail_cache.ttl == 600
    assert static_cache.maxsize == 16
    assert static_cache.ttl == 86400


def test_warmup_returns_count():
    # 清理旧的预热痕迹
    invalidate("*")
    r = warmup()
    assert "warmed" in r
    # warmup 应至少插入 5 个最热键
    assert r["warmed"] >= 5


def test_invalidate_hits_all_three_caches():
    list_cache["test:k1"] = "v1"
    detail_cache["test:k1"] = "v2"
    static_cache["test:k1"] = "v3"
    result = invalidate("test:*")
    assert result["list"] >= 1
    assert result["detail"] >= 1
    assert result["static"] >= 1
    assert "test:k1" not in list_cache
    assert "test:k1" not in detail_cache
    assert "test:k1" not in static_cache


def test_stats_returns_all_three():
    out = stats()
    assert "list" in out
    assert "detail" in out
    assert "static" in out
    for k in ("size", "maxsize", "ttl", "hits", "misses"):
        assert k in out["list"]


# ---------------------------------------------------------------------------
# 9. keys() 接口
# ---------------------------------------------------------------------------
def test_keys_returns_all_keys():
    c = TTLCache(maxsize=10, ttl=60)
    c["a"] = 1
    c["b"] = 2
    keys = c.keys()
    assert set(keys) == {"a", "b"}

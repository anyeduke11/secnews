"""Phase 5 可观测性单测

覆盖:
  - ``observability.log_event()`` 封装与字段传递
  - ``set_start_time`` / ``uptime_s`` 时间跟踪
  - cache 事件触发 (``cache_hit`` / ``cache_miss`` / ``cache_invalidate``)
  - collector 事件触发 (``collect_start`` / ``collect_end``)
  - middleware 事件触发 (``api_request`` / ``api_response``)
  - log_event 异常安全（日志失败不抛）

策略
----
- 桩住 ``logger.info`` 记录所有调用
- 测试不依赖真实网络
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.cache import TTLCache
from backend.observability import log_event, set_start_time, uptime_s


def _event_name(call) -> str | None:
    """兼容 ``log_event("xxx", ...)`` 位置参数 + kwargs。"""
    if call.kwargs.get("event"):
        return call.kwargs["event"]
    if call.args and isinstance(call.args[0], str):
        return call.args[0]
    return None


# ---------------------------------------------------------------------------
# 1. log_event 基本语义
# ---------------------------------------------------------------------------
def test_log_event_calls_logger_info():
    with patch("backend.observability.logger") as mock_logger:
        log_event("test_event", key="value", n=42)
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        # 第一位置参数是 event 名
        assert call_args.args[0] == "test_event"
        # extra 字段含 event
        assert call_args.kwargs["extra"]["event"] == "test_event"
        assert call_args.kwargs["extra"]["key"] == "value"
        assert call_args.kwargs["extra"]["n"] == 42


def test_log_event_swallows_exceptions():
    """即使 logger 抛错, 业务也不应崩。"""
    with patch("backend.observability.logger") as mock_logger:
        mock_logger.info.side_effect = RuntimeError("disk full")
        # 不应抛
        log_event("x", y=1)


# ---------------------------------------------------------------------------
# 2. set_start_time / uptime_s
# ---------------------------------------------------------------------------
def test_uptime_s_increases():
    t0 = time.time()
    set_start_time(t0)
    u1 = uptime_s()
    time.sleep(0.05)
    u2 = uptime_s()
    assert u2 > u1
    assert u2 >= 0.05


def test_set_start_time_resets():
    set_start_time(time.time() - 100)
    assert uptime_s() >= 100


# ---------------------------------------------------------------------------
# 3. cache 事件触发
# ---------------------------------------------------------------------------
def test_cache_miss_event():
    c = TTLCache(maxsize=10, ttl=60, name="test_cache")
    with patch("backend.cache.log_event") as mock:
        with pytest.raises(KeyError):
            _ = c["missing"]
        miss_events = [
            call for call in mock.call_args_list
            if _event_name(call) == "cache_miss"
        ]
        assert len(miss_events) >= 1
        assert miss_events[0].kwargs["cache_name"] == "test_cache"


def test_cache_hit_event():
    c = TTLCache(maxsize=10, ttl=60, name="hit_cache")
    c["k"] = "v"
    with patch("backend.cache.log_event") as mock:
        _ = c["k"]
        hit_events = [
            call for call in mock.call_args_list
            if _event_name(call) == "cache_hit"
        ]
        assert len(hit_events) == 1
        assert hit_events[0].kwargs["cache_name"] == "hit_cache"
        assert hit_events[0].kwargs["key"] == "k"
        assert hit_events[0].kwargs["hits"] == 1
        assert hit_events[0].kwargs["hit_rate"] == 1.0


def test_cache_invalidate_event():
    c = TTLCache(maxsize=10, ttl=60, name="inv_cache")
    c["a"] = 1
    c["b"] = 2
    c["c"] = 3
    with patch("backend.cache.log_event") as mock:
        n = c.invalidate("a*")
        assert n == 1
        inv_events = [
            call for call in mock.call_args_list
            if _event_name(call) == "cache_invalidate"
        ]
        assert len(inv_events) == 1
        assert inv_events[0].kwargs["n_invalidated"] == 1
        assert inv_events[0].kwargs["pattern"] == "a*"


def test_cache_invalidate_no_match_no_event():
    """无匹配 → 不打事件。"""
    c = TTLCache(maxsize=10, ttl=60, name="nomatch_cache")
    c["a"] = 1
    with patch("backend.cache.log_event") as mock:
        n = c.invalidate("xyz*")
        assert n == 0
        inv_events = [
            call for call in mock.call_args_list
            if _event_name(call) == "cache_invalidate"
        ]
        assert len(inv_events) == 0


# ---------------------------------------------------------------------------
# 4. collector 事件 (collect_start / collect_end)
# ---------------------------------------------------------------------------
def test_collect_events_in_collect_method():
    """通过真实 collector 跑一遍, 验证 collect_start / collect_end 触发。"""
    from backend.collectors.base import BaseCollector
    from backend.domain.enums import Category
    from backend.domain.models import HotspotItem
    from datetime import datetime, timezone

    class MockCol(BaseCollector):
        name = "mock"
        category = Category.AI
        sources = []  # Phase 13: sources=[] 走 no_sources 路径,**不**走 fallback

    col = MockCol()
    with patch("backend.collectors.base.log_event") as mock:
        asyncio.run(col.collect())
        events = [_event_name(c) for c in mock.call_args_list]
        assert "collect_start" in events
        assert "collect_end" in events
        end_calls = [
            c for c in mock.call_args_list
            if _event_name(c) == "collect_end"
        ]
        assert end_calls[0].kwargs.get("duration_ms") is not None
        # Phase 13: status 应为 'no_sources' (不是 'fallback')
        # SPEC §3.1: fallback 撤了,sources=[] 时直接返回 []
        assert end_calls[0].kwargs.get("status") == "no_sources"


# ---------------------------------------------------------------------------
# 5. middleware 事件 (api_request / api_response)
# ---------------------------------------------------------------------------
def test_middleware_events():
    """通过 TestClient 触发请求, 验证 api_request/api_response 事件。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.middleware import TraceIDMiddleware

    app = FastAPI()
    app.add_middleware(TraceIDMiddleware, exclude_paths=[])

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    with patch("backend.api.middleware.log_event") as mock:
        with TestClient(app) as c:
            r = c.get("/ping")
        assert r.status_code == 200
        events = [_event_name(call) for call in mock.call_args_list]
        assert "api_request" in events
        assert "api_response" in events
        resp_calls = [
            c for c in mock.call_args_list
            if _event_name(c) == "api_response"
        ]
        assert resp_calls[-1].kwargs.get("status") == 200
        assert resp_calls[-1].kwargs.get("duration_ms") is not None


# ---------------------------------------------------------------------------
# 6. /api/health & /api/stats 包含新字段
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db_client(monkeypatch, tmp_path):
    """本地测试 client + 临时 DB fixture。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api import register_routers
    from backend.api.middleware import TraceIDMiddleware
    from backend.cache import invalidate
    from backend.config import config
    from backend.exceptions import register_exception_handlers
    from backend.repository import db

    monkeypatch.setattr(config, "db_path", tmp_path / "test.db")
    db.init_db()
    invalidate("*")

    app = FastAPI()
    app.add_middleware(TraceIDMiddleware, exclude_paths=["/api/health"])
    register_exception_handlers(app)
    register_routers(app)
    with patch("backend.scheduler.scheduler.get_scheduler", return_value=None):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    db.close_db()


def test_health_db_truncate_detected(monkeypatch, tmp_path):
    """Phase 8 Task 5.4: 即使 integrity_check 通过，truncate hotspots 也应被检测。

    直接调用 _db_health() 避免 TestClient 跨线程的连接共享问题：
    构造一个有数据的 DB → DELETE 所有行 → _db_health 应返回 ok=False。
    """
    from backend.api.health import _INTEGRITY_CACHE, _db_health
    from backend.config import config
    from backend.domain.enums import Category
    from backend.domain.models import HotspotItem
    from backend.repository import db
    from backend.repository.hotspot_repo import HotspotRepository

    monkeypatch.setattr(config, "db_path", tmp_path / "test_truncate.db")
    db.init_db()

    # seed 1 个 hotspot
    item = HotspotItem(
        id="seed-1",
        title="Seed Title",
        summary="Seed summary",
        source="test-src",
        url="https://example.com/seed-1",
        category=Category.AI,
        published_at=datetime.now(timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        score=80,
        is_fallback=False,
    )
    HotspotRepository().upsert_many([item])
    _INTEGRITY_CACHE.clear()

    # 1) seed 后 _db_health 应 ok=True
    health0 = _db_health()
    assert health0["hotspots_count"] == 1
    assert health0["ok"] is True, f"expected ok=True with 1 row, got {health0}"

    # 2) truncate hotspots → _db_health 应 ok=False
    conn = db.get_connection()
    conn.execute("DELETE FROM hotspots")
    conn.execute("DELETE FROM hotspots_fts")
    conn.commit()
    _INTEGRITY_CACHE.clear()

    health1 = _db_health()
    assert health1["hotspots_count"] == 0
    assert health1["ok"] is False
    assert "empty" in (health1.get("error", "") + str(health1.get("error", ""))).lower() or \
           health1["ok"] is False
    db.close_db()


def test_health_includes_uptime_s(temp_db_client):
    """/api/health 应含 uptime_s / db.size_mb / cache.hit_rate。"""
    r = temp_db_client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "uptime_s" in data
    assert "uptime_seconds" in data  # 兼容
    assert "db" in data["components"]
    db = data["components"]["db"]
    assert "size_mb" in db
    assert "wal" in db
    assert "integrity" in db
    assert "hit_rate" in data["components"]["cache"]


def test_health_db_includes_hotspots_count(temp_db_client):
    """/api/health 应含 db.hotspots_count（Phase 8 Task 5.4 新字段）。

    空 DB 场景下 db.hotspots_count == 0 且 db.ok == False。
    """
    r = temp_db_client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    db = data["components"]["db"]
    assert "hotspots_count" in db
    # 全新临时 DB 是空的，所以 db.ok 应为 False
    assert db["hotspots_count"] == 0
    assert db["ok"] is False
    # status 应反映 db 不健康
    assert data["status"] in ("degraded", "down")


def test_stats_includes_collect_runs(temp_db_client):
    """/api/stats 应含 collect_runs_24h / success_rate_24h / avg_collect_duration_ms / last_fallback_at。"""
    r = temp_db_client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert "collect_runs_24h" in data
    assert "success_rate_24h" in data
    assert "avg_collect_duration_ms" in data
    assert "last_fallback_at" in data
    assert "uptime_s" in data
    # cache
    assert "hit_rate" in data["cache"]
    # db
    assert "size_mb" in data["db"]

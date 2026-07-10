"""Phase 6 数据一致性校验单测。

覆盖 /api/stats 的 ``consistency_check`` 字段：
  - 空 DB → status 为 ok/unknown, drift 为空
  - 每个 category 1 条 → status == 'ok'
  - 字段结构稳定
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.cache import invalidate
from backend.config import config
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.repository.hotspot_repo import HotspotRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db_client(monkeypatch, tmp_path):
    """本地测试 client + 临时 DB fixture。"""
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


def _make_item(id_: str, cat: Category) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=f"title {id_}",
        source="src",
        url=f"https://example.com/{id_}",
        category=cat,
        published_at=now,
        fetched_at=now,
    )


# ---------------------------------------------------------------------------
# 1. /api/stats 包含 consistency_check 字段
# ---------------------------------------------------------------------------
def test_stats_includes_consistency_check(temp_db_client):
    """/api/stats 应包含 consistency_check 字段。"""
    r = temp_db_client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert "consistency_check" in data
    cc = data["consistency_check"]
    assert "status" in cc
    assert "drift" in cc
    assert cc["status"] in ("ok", "drift", "unknown")
    assert isinstance(cc["drift"], list)


# ---------------------------------------------------------------------------
# 2. 空 DB → consistency_check.status 合法（ok/unknown），drift 为空
# ---------------------------------------------------------------------------
def test_stats_consistency_check_empty(temp_db_client):
    """空 DB：consistency_check 字段存在, status ∈ {ok, unknown}, drift == []"""
    r = temp_db_client.get("/api/stats")
    assert r.status_code == 200
    cc = r.json()["consistency_check"]
    assert cc["status"] in ("ok", "unknown")
    assert cc["drift"] == []


# ---------------------------------------------------------------------------
# 3. 每分类 1 条 → consistency_check.status == 'ok'
# ---------------------------------------------------------------------------
def test_stats_consistency_check_ok(temp_db_client):
    """每个 category 1 条数据：一致性校验应为 ok。"""
    repo = HotspotRepository()
    items = [
        _make_item(f"a-{cat.value}", cat)
        for cat in Category
    ]
    repo.upsert_many(items)

    r = temp_db_client.get("/api/stats")
    assert r.status_code == 200
    cc = r.json()["consistency_check"]
    assert cc["status"] == "ok"
    assert cc["drift"] == []


# ---------------------------------------------------------------------------
# 4. 字段结构稳定性
# ---------------------------------------------------------------------------
def test_stats_consistency_check_field_shape(temp_db_client):
    """consistency_check 字段必须含 status + drift（结构稳定）。"""
    r = temp_db_client.get("/api/stats")
    assert r.status_code == 200
    cc = r.json()["consistency_check"]
    # 必有字段
    assert "status" in cc
    assert "drift" in cc
    # status 类型为字符串
    assert isinstance(cc["status"], str)
    # drift 类型为 list
    assert isinstance(cc["drift"], list)


# ---------------------------------------------------------------------------
# 5. /api/stats 仍能正常返回其它字段（向后兼容）
# ---------------------------------------------------------------------------
def test_stats_backward_compatible_with_consistency_check(temp_db_client):
    """/api/stats 在加 consistency_check 后仍保留其它字段。"""
    r = temp_db_client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    # 原有字段
    assert "collect_runs_24h" in data
    assert "success_rate_24h" in data
    assert "avg_collect_duration_ms" in data
    assert "last_fallback_at" in data
    assert "uptime_s" in data
    # 新字段
    assert "consistency_check" in data

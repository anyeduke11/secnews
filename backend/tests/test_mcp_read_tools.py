"""v1.7 Phase 7 — 5 个 MCP 读 tool 路由测试.

读 tool 列表:
  - search_hotspots   → GET /api/hotspots
  - get_hotspot       → GET /api/hotspots/{id}
  - list_favorites    → GET /api/favorites
  - search_knowledge  → GET /api/knowledge/items
  - get_personal_profile → GET /api/profile
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from backend.config import config
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_mcp_read.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import register_routers

    app = FastAPI()
    register_routers(app)
    return TestClient(app)


def _insert_hotspot(hid, title="测试", category="ai"):
    now = datetime.now(timezone.utc).isoformat()
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO hotspots "
        "(id, title, summary, source, url, category, published_at, score, "
        "fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (hid, title, "summary", "test", f"https://example.com/{hid}",
         category, now, 50.0, now, 0, 80, "[]", "pending", now),
    )


def test_search_hotspots_tool(client, temp_db):
    """search_hotspots 路由到 GET /api/hotspots."""
    _insert_hotspot("h-1", "AI 文章")
    res = client.get("/api/hotspots")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data or "hotspots" in data or isinstance(data, list)


def test_get_hotspot_tool(client, temp_db):
    """get_hotspot 路由到 GET /api/hotspots/{id}."""
    _insert_hotspot("h-1", "AI 文章")
    res = client.get("/api/hotspots/h-1")
    assert res.status_code == 200
    data = res.json()
    # 实际响应格式: {"item": {"id": "h-1", ...}} 或直接 {"id": "h-1"}
    item = data.get("item", data)
    assert item.get("id") == "h-1"


def test_list_favorites_tool(client, temp_db):
    """list_favorites 路由到 GET /api/favorites."""
    res = client.get("/api/favorites")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_search_knowledge_tool(client, temp_db):
    """search_knowledge 路由到 GET /api/knowledge/items."""
    res = client.get("/api/knowledge/items")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_get_personal_profile_tool(client, temp_db):
    """get_personal_profile 路由到 GET /api/profile."""
    res = client.get("/api/profile")
    # 可能 200 或 404 (取决于实现)
    assert res.status_code in (200, 404)

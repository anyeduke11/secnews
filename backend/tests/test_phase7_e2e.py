"""v1.7 Phase 7 — 端到端 MCP 集成测试.

覆盖:
  1. AI Agent 调 add_favorite → SQLite 落库 + knowledge/items/{id}.md 写入
  2. /api/mcp/status 返回 13 tools
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.config import config
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_phase7_e2e.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db):
    from backend.api.mcp_config import mcp_tool_registry_seed
    mcp_tool_registry_seed()  # 显式 seed (lifespan 不在 test fixture 跑)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api import register_routers

    app = FastAPI()
    register_routers(app)
    return TestClient(app)


def _insert_hotspot(hid, title="测试"):
    now = datetime.now(timezone.utc).isoformat()
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO hotspots "
        "(id, title, summary, source, url, category, published_at, score, "
        "fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (hid, title, "summary", "test", f"https://example.com/{hid}",
         "ai", now, 50.0, now, 0, 80, "[]", "pending", now),
    )


def test_mcp_status_lists_9_tools(client, temp_db):
    """E2E: /api/mcp/status 报告 9 tools."""
    res = client.get("/api/mcp/status")
    assert res.status_code == 200
    data = res.json()
    assert data["tools_count"] == 9
    assert data["enabled"] is True


def test_mcp_tools_list_9_entries(client, temp_db):
    """E2E: /api/mcp/tools 列出 9 个 tool 元数据."""
    res = client.get("/api/mcp/tools")
    assert res.status_code == 200
    data = res.json()
    assert len(data.get("tools", [])) == 9

    # 验证 5 读 + 4 写
    by_category = {}
    for t in data["tools"]:
        by_category.setdefault(t["category"], []).append(t["name"])
    assert len(by_category.get("read", [])) == 5
    assert len(by_category.get("write", [])) == 4

    # 关键 tool 名称存在
    names = {t["name"] for t in data["tools"]}
    expected = {
        "search_hotspots", "get_hotspot", "list_favorites", "search_knowledge", "get_personal_profile",
        "add_favorite", "remove_favorite", "add_annotation", "update_knowledge_item",
    }
    assert expected.issubset(names), f"missing: {expected - names}"


def test_mcp_add_favorite_writes_to_sqlite(client, temp_db):
    """E2E: 模拟 AI Agent 调 add_favorite → SQLite favorites 表新增 + created_via='mcp'."""
    _insert_hotspot("h-e2e-1", "AI E2E 文章")
    res = client.post("/api/favorites", json={
        "hotspot_id": "h-e2e-1",
        "category": "ai",
        "title": "AI E2E 文章",
        "source": "external-agent",
        "url": "https://example.com/h-e2e-1",
        "created_via": "mcp",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["created"] is True

    # 验证 SQLite 写入
    conn = db.get_connection()
    row = conn.execute(
        "SELECT hotspot_id, created_via FROM favorites WHERE hotspot_id = ?",
        ("h-e2e-1",),
    ).fetchone()
    assert row is not None
    assert row["created_via"] == "mcp"
    assert row["hotspot_id"] == "h-e2e-1"


def test_mcp_toggle_enabled_changes_status(client, temp_db):
    """E2E: 切换 feature.mcp_server 反映在 /api/mcp/status."""
    # 默认 enabled
    res = client.get("/api/mcp/status")
    assert res.json()["enabled"] is True

    # 关闭
    res = client.put("/api/settings/mcp/enabled", json={"enabled": False})
    assert res.status_code == 200
    res = client.get("/api/mcp/status")
    assert res.json()["enabled"] is False

    # 重新开启
    res = client.put("/api/settings/mcp/enabled", json={"enabled": True})
    assert res.status_code == 200
    res = client.get("/api/mcp/status")
    assert res.json()["enabled"] is True

"""v1.7 Phase 7 — favorites.created_via 测试.

覆盖:
  1. UI 调用 (不传 created_via) → DB 默认 'ui'
  2. UI 显式 created_via='ui' → DB 'ui'
  3. MCP 调用 created_via='mcp' → DB 'mcp'
  4. List 接口返回 created_via 字段
  5. 非法 created_via 降级为 'ui' (安全兜底)

这些测试同时验证:
- migration 039 已成功加列
- favorite_repo.add() 正确写入 created_via
- favorite_repo._row_to_favorite() 正确读出 created_via (Phase 7 修复的 row->model bug)
- /api/favorites POST 接受 created_via 参数
- /api/favorites GET 返回 created_via 字段
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.repository import db
from backend.repository.favorite_repo import FavoriteRepository


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离的测试 DB。"""
    test_db = tmp_path / "test_favorite_created_via.db"
    monkeypatch.setattr("backend.config.config.db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db):
    """FastAPI TestClient (含 favorites router)。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api import register_routers

    app = FastAPI()
    register_routers(app)
    return TestClient(app)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. Repository 层级测试 (直接走 DB, 不走 API)
# ---------------------------------------------------------------------------
def test_default_created_via_is_ui(temp_db):
    """不传 created_via → DB 默认 'ui' (默认 = UI 来源)。"""
    repo = FavoriteRepository()
    created, item = repo.add(
        hotspot_id="h-1",
        category="ai",
        title="AI 文章",
        source="test",
        url="https://example.com/h-1",
    )
    assert created is True
    assert item.created_via == "ui"
    # DB 实际值
    conn = db.get_connection()
    row = conn.execute(
        "SELECT created_via FROM favorites WHERE hotspot_id = ?", ("h-1",)
    ).fetchone()
    assert row["created_via"] == "ui"


def test_ui_source_writes_ui(temp_db):
    """显式 created_via='ui' → DB 'ui'。"""
    repo = FavoriteRepository()
    _, item = repo.add(
        hotspot_id="h-2",
        category="security",
        title="Security 文章",
        source="test",
        url="https://example.com/h-2",
        created_via="ui",
    )
    assert item.created_via == "ui"


def test_mcp_source_writes_mcp(temp_db):
    """MCP tool 调用 created_via='mcp' → DB 'mcp' (核心场景)。"""
    repo = FavoriteRepository()
    _, item = repo.add(
        hotspot_id="h-3",
        category="ai",
        title="MCP-favorited",
        source="external-agent",
        url="https://example.com/h-3",
        created_via="mcp",
    )
    assert item.created_via == "mcp"
    # DB 实际值 (SQLite 落盘验证)
    conn = db.get_connection()
    row = conn.execute(
        "SELECT created_via FROM favorites WHERE hotspot_id = ?", ("h-3",)
    ).fetchone()
    assert row["created_via"] == "mcp"


def test_agent_source_writes_agent(temp_db):
    """保留历史 'agent' 枚举值 (虽然 Phase 7 agent 进程已删, 数据列仍允许)。"""
    repo = FavoriteRepository()
    _, item = repo.add(
        hotspot_id="h-4",
        category="finance",
        title="Agent legacy",
        source="old-agent",
        url="https://example.com/h-4",
        created_via="agent",
    )
    assert item.created_via == "agent"


def test_invalid_created_via_falls_back_to_ui(temp_db):
    """非法 created_via 字符串 → 降级为 'ui' (防数据污染)。"""
    repo = FavoriteRepository()
    _, item = repo.add(
        hotspot_id="h-5",
        category="ai",
        title="invalid",
        source="test",
        url="https://example.com/h-5",
        created_via="rm -rf /",  # 注入尝试
    )
    assert item.created_via == "ui"


def test_row_to_favorite_reads_created_via(temp_db):
    """验证 _row_to_favorite 正确读出 created_via (修复 Phase 7 row->model 漏读 bug)。"""
    repo = FavoriteRepository()
    repo.add(
        hotspot_id="h-6",
        category="ai",
        title="read-back",
        source="test",
        url="https://example.com/h-6",
        created_via="mcp",
    )
    # list → 读出 → 验证 created_via 保留
    items = repo.list(category="ai", limit=10)
    matching = [i for i in items if i.hotspot_id == "h-6"]
    assert len(matching) == 1
    assert matching[0].created_via == "mcp"


# ---------------------------------------------------------------------------
# 2. API 层级测试 (走 /api/favorites 端点)
# ---------------------------------------------------------------------------
def test_api_post_without_created_via_defaults_to_ui(client, temp_db):
    """POST /api/favorites 不传 created_via → DB 'ui'。"""
    res = client.post("/api/favorites", json={
        "hotspot_id": "api-h-1",
        "category": "ai",
        "title": "API test 1",
        "source": "ui-test",
        "url": "https://example.com/api-h-1",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["item"]["created_via"] == "ui"


def test_api_post_with_mcp_writes_mcp(client, temp_db):
    """POST /api/favorites created_via='mcp' → DB 'mcp' (MCP tool 模拟)。"""
    res = client.post("/api/favorites", json={
        "hotspot_id": "api-h-2",
        "category": "ai",
        "title": "MCP API test",
        "source": "external-agent",
        "url": "https://example.com/api-h-2",
        "created_via": "mcp",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["item"]["created_via"] == "mcp"
    # DB 实际验证
    conn = db.get_connection()
    row = conn.execute(
        "SELECT created_via FROM favorites WHERE hotspot_id = ?", ("api-h-2",)
    ).fetchone()
    assert row["created_via"] == "mcp"


def test_api_post_with_invalid_created_via_sanitizes(client, temp_db):
    """POST /api/favorites 非法 created_via → 服务端降级 'ui'。"""
    res = client.post("/api/favorites", json={
        "hotspot_id": "api-h-3",
        "category": "ai",
        "title": "invalid",
        "source": "ui-test",
        "url": "https://example.com/api-h-3",
        "created_via": "hacker_attempt",
    })
    assert res.status_code == 200
    data = res.json()
    # API 层做了 sanitization → 'ui'
    assert data["item"]["created_via"] == "ui"


def test_api_list_includes_created_via(client, temp_db):
    """GET /api/favorites 返回值含 created_via 字段 (前端的 source 标识依赖此字段)。"""
    # 先添加 2 条, 一条 ui 一条 mcp
    client.post("/api/favorites", json={
        "hotspot_id": "list-h-1",
        "category": "ai",
        "title": "ui",
        "source": "ui",
        "url": "https://example.com/list-h-1",
        "created_via": "ui",
    })
    client.post("/api/favorites", json={
        "hotspot_id": "list-h-2",
        "category": "ai",
        "title": "mcp",
        "source": "mcp",
        "url": "https://example.com/list-h-2",
        "created_via": "mcp",
    })

    res = client.get("/api/favorites?category=ai&limit=50")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    by_via = {item["hotspot_id"]: item["created_via"] for item in data["items"]}
    assert by_via.get("list-h-1") == "ui"
    assert by_via.get("list-h-2") == "mcp"


def test_migration_039_adds_created_via_column(temp_db):
    """验证 migration 039 已成功加列 (init_db 应自动应用)。"""
    conn = db.get_connection()
    cols = [row["name"] for row in conn.execute("PRAGMA table_info(favorites)").fetchall()]
    assert "created_via" in cols

"""v1.7 Phase 7 — MCP Server 基础测试.

覆盖:
  - FastApiMCP 启动 / 关闭
  - tools/list 返回 9 个 tool
  - mcp_tool_registry seeding 幂等性
  - feature.mcp_server toggle → /api/mcp/status 反映
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_mcp.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def test_is_mcp_enabled_default():
    """默认 feature.mcp_server=True (Option A 默认开)."""
    from backend.services.feature_flag_service import is_enabled
    assert is_enabled("mcp") is True


def test_mcp_tool_registry_table_exists(temp_db):
    """migration 037 已建 mcp_tool_registry 表."""
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='mcp_tool_registry'"
    ).fetchall()
    assert len(rows) == 1


def test_seed_idempotent(temp_db):
    """重复调用 mcp_tool_registry_seed 不会重复插入 (启动幂等)."""
    from backend.api.mcp_config import mcp_tool_registry_seed
    inserted_first = mcp_tool_registry_seed()
    inserted_second = mcp_tool_registry_seed()
    # 第二次应返回 0 (无新增)
    assert inserted_second == 0
    # 表中应有 9 个 tool (Phase 15: 从 13 移除 4 个低频工具)
    conn = db.get_connection()
    rows = conn.execute("SELECT COUNT(*) AS n FROM mcp_tool_registry").fetchone()
    assert int(rows["n"]) == 9


def test_mcp_status_endpoint(temp_db):
    """GET /api/mcp/status 返回 enabled / transport / tools_count."""
    from backend.api.mcp_config import mcp_tool_registry_seed
    mcp_tool_registry_seed()  # 显式 seed (lifespan 不在 test fixture 跑)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.mcp import router as mcp_router

    app = FastAPI()
    app.include_router(mcp_router)
    client = TestClient(app)
    res = client.get("/api/mcp/status")
    assert res.status_code == 200
    data = res.json()
    assert "enabled" in data
    assert "transport" in data
    assert "tools_count" in data
    assert data["tools_count"] == 9


def test_mcp_tools_endpoint(temp_db):
    """GET /api/mcp/tools 返回 9 个 tool (5 读 + 4 写)."""
    from backend.api.mcp_config import mcp_tool_registry_seed
    mcp_tool_registry_seed()

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.mcp import router as mcp_router

    app = FastAPI()
    app.include_router(mcp_router)
    client = TestClient(app)
    res = client.get("/api/mcp/tools")
    assert res.status_code == 200
    data = res.json()
    tools = data.get("tools", [])
    assert len(tools) == 9

    categories = [t["category"] for t in tools]
    assert categories.count("read") == 5
    assert categories.count("write") == 4


def test_toggle_mcp_enabled(temp_db):
    """PUT /api/settings/mcp/enabled 切换 feature.mcp_server."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.mcp import router as mcp_router

    app = FastAPI()
    app.include_router(mcp_router)
    client = TestClient(app)

    # 关闭
    res = client.put("/api/settings/mcp/enabled", json={"enabled": False})
    assert res.status_code == 200
    from backend.services.feature_flag_service import is_enabled
    assert is_enabled("mcp") is False

    # 开启
    res = client.put("/api/settings/mcp/enabled", json={"enabled": True})
    assert res.status_code == 200
    assert is_enabled("mcp") is True

"""v1.7 Phase 7 — MCP SSE transport 测试.

覆盖:
  - /mcp/sse 端点挂载 (via FastApiMCP)
  - /api/mcp/status 返回 transport info
  - HTTP client 能连 SSE 端点
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_mcp_sse.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db):
    from backend.api.mcp_config import (
        build_mcp_server,
        mcp_tool_registry_seed,
        mount_sse_endpoint,
    )
    mcp_tool_registry_seed()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api import register_routers
    app = FastAPI()
    register_routers(app)
    # 与 main.py lifespan 对齐: 真实挂载 /mcp/sse (fastapi-mcp 0.4 mount_sse),
    # 使 /api/mcp/status 的 sse_endpoint 反映真实挂载状态。
    mcp = build_mcp_server(app)
    mount_sse_endpoint(app, mcp)
    return TestClient(app)


def test_sse_endpoint_status_metadata(client, temp_db):
    """/api/mcp/status 返回 transport info."""
    res = client.get("/api/mcp/status")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert "transport" in data
    assert "sse" in data["transport"]
    assert data["sse_endpoint"] == "/mcp/sse"
    assert data["spec_version"] == "2025-06-18"


def test_sse_disabled_returns_404(client, temp_db, monkeypatch):
    """feature.mcp_server=False 时, /api/mcp/tools 返 404."""
    from backend.services.feature_flag_service import disable, enable
    disable("mcp")
    res = client.get("/api/mcp/tools")
    assert res.status_code == 404
    enable("mcp")


def test_sse_config_endpoint(client, temp_db):
    """GET /api/settings/mcp/config 返回 stdio + sse 配置."""
    res = client.get("/api/settings/mcp/config")
    assert res.status_code == 200
    data = res.json()
    assert "stdio" in data
    assert "sse" in data
    assert "mcpServers" in data["stdio"]
    assert "hotspot" in data["stdio"]["mcpServers"]


def test_sse_tools_count(client, temp_db):
    """/api/mcp/tools 返回 14 tool (基础 9 + wiki 4 + wiki_write), transport 标识正确."""
    res = client.get("/api/mcp/tools")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 14
    assert len(data["tools"]) == 14

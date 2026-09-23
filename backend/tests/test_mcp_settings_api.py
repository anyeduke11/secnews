"""mcp_settings_api — ungated MCP 设置端点测试 (migration: 自锁解除 + 持久化)。

验收 (设计稿 §4.1/4.2):
- extensions.mcp=false (TOML 默认) 时 PUT /api/settings/mcp/enabled 仍 200 — 不再自锁
- enable 写 settings kv feature.mcp (config.feature_mcp 的 kv 镜像, 重启回读), 响应 note 如实
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.exceptions import register_exception_handlers
from backend.repository import db


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_mcp_settings.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db) -> TestClient:
    # 关键: 不 monkeypatch extensions.mcp — 新端点不依赖该 gate 注册 (ungated 基础设施)
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


class TestMcpSettingsUngated:
    def test_put_enabled_reachable_when_gate_off(self, client, monkeypatch):
        monkeypatch.setattr(config, "feature_mcp", True)
        r = client.put("/api/settings/mcp/enabled", json={"enabled": False})
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False
        assert body["persisted"] is True
        assert "重启" not in body["note"]  # server 开关立即生效, note 不再误导

    def test_toggle_persists_to_settings_kv(self, client, monkeypatch):
        monkeypatch.setattr(config, "feature_mcp", True)
        client.put("/api/settings/mcp/enabled", json={"enabled": False})
        from backend.repository.settings_repo import SettingsRepository
        assert SettingsRepository().get("feature.mcp") is False

    def test_get_config_still_gated_404(self, client, monkeypatch):
        # 读配置依赖 MCP server 本体, feature_mcp=false → 404 (与旧契约一致)
        monkeypatch.setattr(config, "feature_mcp", False)
        r = client.get("/api/settings/mcp/config")
        assert r.status_code == 404

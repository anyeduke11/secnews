"""settings_flags_api — 能力开关读写端点测试 (设计稿 §4.3)。"""
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
    test_db = tmp_path / "test_settings_flags.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db) -> TestClient:
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


class TestFeatureGates:
    def test_get_lists_16_gates_with_source(self, client):
        r = client.get("/api/settings/feature-gates")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 16
        item = next(i for i in items if i["name"] == "mcp")
        assert item["source"] in ("default", "toml", "env")
        assert item["effective_scope"] in ("runtime", "startup")

    def test_put_unknown_gate_404(self, client):
        r = client.put("/api/settings/feature-gates/nope", json={"enabled": True})
        assert r.status_code == 404

    def test_put_writes_toml_and_audits(self, client, tmp_path, monkeypatch):
        toml_path = tmp_path / "feature_gates.toml"
        toml_path.write_text('[extensions]\nsecnews = true\nmcp = false\n')
        import backend.extensions as ext
        monkeypatch.setattr(ext, "_GATES_PATH", toml_path)
        # conftest autouse 注入的 all-on env 会触发 409 — 清掉以走 TOML 写入路径
        monkeypatch.delenv("HOTSPOT_FEATURE_GATES", raising=False)
        r = client.put("/api/settings/feature-gates/mcp", json={"enabled": True})
        assert r.status_code == 200
        assert "mcp = true" in toml_path.read_text()

    def test_put_env_overridden_409(self, client, tmp_path, monkeypatch):
        toml_path = tmp_path / "feature_gates.toml"
        toml_path.write_text('[extensions]\nmcp = false\n')
        import backend.extensions as ext
        monkeypatch.setattr(ext, "_GATES_PATH", toml_path)
        monkeypatch.setenv("HOTSPOT_FEATURE_GATES", '{"extensions":{"mcp":true}}')
        r = client.put("/api/settings/feature-gates/mcp", json={"enabled": False})
        assert r.status_code == 409
        assert "HOTSPOT_FEATURE_GATES" in r.json()["message"]

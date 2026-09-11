"""DEV-0176 — 兴趣画像 API 测试 (Workbench Focus PRD P0.3)。

覆盖:
- GET /api/settings/interests 默认空画像
- PATCH 写入 → GET 回读一致
- PATCH 未知域 → 400 (InvalidParamException 契约)
- PATCH 去重保序 + 空数组清空
- PATCH 落 audit_log (经 /api/observability/audit 只读端点断言)
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

_AUDIT_ACTION = "workbench.interests.set"


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_settings_interests.db"
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


class TestInterestsAPI:
    def test_get_default_empty(self, client):
        r = client.get("/api/settings/interests")
        assert r.status_code == 200
        body = r.json()
        assert body["domains"] == []
        assert len(body["valid_domains"]) == 8
        assert set(body["labels"].keys()) == set(body["valid_domains"])

    def test_patch_then_get_roundtrip(self, client):
        domains = ["ai_security", "vuln_research"]
        r = client.patch("/api/settings/interests", json={"domains": domains, "actor": "test"})
        assert r.status_code == 200
        assert r.json()["domains"] == domains

        r2 = client.get("/api/settings/interests")
        assert r2.json()["domains"] == domains

    def test_patch_unknown_domain_rejected(self, client):
        r = client.patch("/api/settings/interests", json={"domains": ["crypto_trading"]})
        assert r.status_code == 400
        assert "unknown practice domains" in str(r.json())

    def test_patch_dedupes_preserving_order(self, client):
        r = client.patch(
            "/api/settings/interests",
            json={"domains": ["appsec", "compliance", "appsec"]},
        )
        assert r.status_code == 200
        assert r.json()["domains"] == ["appsec", "compliance"]

    def test_patch_empty_clears(self, client):
        client.patch("/api/settings/interests", json={"domains": ["appsec"]})
        r = client.patch("/api/settings/interests", json={"domains": []})
        assert r.status_code == 200
        assert r.json()["domains"] == []
        assert client.get("/api/settings/interests").json()["domains"] == []

    def test_patch_writes_audit_log(self, client, temp_db):
        client.patch("/api/settings/interests", json={"domains": ["appsec"], "actor": "audit-test"})
        r = client.get("/api/observability/audit", params={"action": _AUDIT_ACTION, "limit": 5})
        assert r.status_code == 200
        items = r.json()["items"]
        assert items, "audit_log 未写入 workbench.interests.set"
        latest = items[0]
        assert latest["actor"] == "audit-test"
        assert latest["target"] == "interest.practice_domains"

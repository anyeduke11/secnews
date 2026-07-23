"""v1.7 Phase 3 — Alerts API 端到端测试.

覆盖:
- 规则 CRUD: POST/GET/PUT/DELETE /api/alerts/rules
- 告警 CRUD: GET /api/alerts, GET/PUT/DELETE /api/alerts/{id}
- 标记已读 / 忽略: PUT /api/alerts/{id}/read, /dismiss
- 手动评估: POST /api/alerts/evaluate/{hotspot_id}
- 校验: 不存在 404, 字段越界 422
"""
from __future__ import annotations

from datetime import datetime, timezone

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
    test_db = tmp_path / "test_alerts_api.db"
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


def _rule_payload(name: str = "FastAPI 告警") -> dict:
    return {
        "name": name,
        "condition": {
            "type": "tag_match",
            "operator": "OR",
            "conditions": [{"op": "contains_any", "value": ["fastapi"]}],
        },
        "action": {"type": "sse"},
        "cooldown_sec": 1800,
        "enabled": True,
    }


def _insert_hotspot(hotspot_id: str, title: str = "FastAPI 漏洞", summary: str = "FastAPI RCE") -> None:
    now = datetime.now(timezone.utc).isoformat()
    from backend.repository.db import get_connection
    get_connection().execute(
        """
        INSERT OR REPLACE INTO hotspots
            (id, title, summary, source, url, category, published_at, score,
             fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hotspot_id, title, summary, "test",
            f"https://example.com/{hotspot_id}",
            "security", now, 50.0, now, 0, 80, "[]", "pending", now,
        ),
    )


class TestRuleCRUD:
    def test_create_rule_returns_201(self, client):
        r = client.post("/api/alerts/rules", json=_rule_payload())
        assert r.status_code == 201
        item = r.json()["item"]
        assert item["name"] == "FastAPI 告警"
        assert item["cooldown_sec"] == 1800
        assert item["enabled"] is True
        assert item["id"].startswith("rule-")
        assert item["condition"]["type"] == "tag_match"

    def test_list_rules(self, client):
        client.post("/api/alerts/rules", json=_rule_payload("规则 A"))
        client.post("/api/alerts/rules", json=_rule_payload("规则 B"))
        r = client.get("/api/alerts/rules")
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_list_rules_enabled_only(self, client):
        client.post("/api/alerts/rules", json={**_rule_payload("启用"), "enabled": True})
        client.post("/api/alerts/rules", json={**_rule_payload("禁用"), "enabled": False})
        r = client.get("/api/alerts/rules", params={"enabled_only": "true"})
        assert r.json()["count"] == 1

    def test_get_rule(self, client):
        created = client.post("/api/alerts/rules", json=_rule_payload()).json()["item"]
        r = client.get(f"/api/alerts/rules/{created['id']}")
        assert r.status_code == 200
        assert r.json()["item"]["id"] == created["id"]

    def test_get_rule_missing_404(self, client):
        assert client.get("/api/alerts/rules/no-such").status_code == 404

    def test_update_rule(self, client):
        created = client.post("/api/alerts/rules", json=_rule_payload()).json()["item"]
        r = client.put(
            f"/api/alerts/rules/{created['id']}",
            json={"name": "更新名称", "cooldown_sec": 600, "enabled": False},
        )
        assert r.status_code == 200
        item = r.json()["item"]
        assert item["name"] == "更新名称"
        assert item["cooldown_sec"] == 600
        assert item["enabled"] is False

    def test_update_rule_missing_404(self, client):
        assert client.put("/api/alerts/rules/no-such", json={"name": "x"}).status_code == 404

    def test_delete_rule(self, client):
        created = client.post("/api/alerts/rules", json=_rule_payload()).json()["item"]
        assert client.delete(f"/api/alerts/rules/{created['id']}").status_code == 200
        assert client.get(f"/api/alerts/rules/{created['id']}").status_code == 404

    def test_delete_rule_missing_404(self, client):
        assert client.delete("/api/alerts/rules/no-such").status_code == 404


class TestAlertListAndRead:
    def _seed_alert(self, client) -> dict:
        """创建规则 + 热点 + 触发评估, 返回生成的告警."""
        client.post("/api/alerts/rules", json=_rule_payload())
        _insert_hotspot("h-api-1")
        # 给热点打 fastapi 标签
        from backend.repository.tags_repo import TagRepository
        TagRepository().add("fastapi", "FastAPI", "framework")
        TagRepository().attach("h-api-1", "fastapi", 0.8)
        # 手动评估
        client.post("/api/alerts/evaluate/h-api-1")
        alerts = client.get("/api/alerts").json()["items"]
        assert alerts, "评估应产生告警"
        return alerts[0]

    def test_list_alerts(self, client):
        self._seed_alert(client)
        r = client.get("/api/alerts")
        assert r.status_code == 200
        assert r.json()["count"] >= 1

    def test_list_alerts_by_status(self, client):
        alert = self._seed_alert(client)
        client.put(f"/api/alerts/{alert['id']}/read")
        pending = client.get("/api/alerts", params={"status": "pending"}).json()
        read = client.get("/api/alerts", params={"status": "read"}).json()
        assert pending["count"] == 0
        assert read["count"] == 1

    def test_get_alert(self, client):
        alert = self._seed_alert(client)
        r = client.get(f"/api/alerts/{alert['id']}")
        assert r.status_code == 200
        assert r.json()["item"]["id"] == alert["id"]

    def test_get_alert_missing_404(self, client):
        assert client.get("/api/alerts/no-such").status_code == 404

    def test_mark_read(self, client):
        alert = self._seed_alert(client)
        r = client.put(f"/api/alerts/{alert['id']}/read")
        assert r.status_code == 200
        assert r.json()["item"]["status"] == "read"

    def test_mark_read_missing_404(self, client):
        assert client.put("/api/alerts/no-such/read").status_code == 404

    def test_dismiss_alert(self, client):
        alert = self._seed_alert(client)
        r = client.put(f"/api/alerts/{alert['id']}/dismiss")
        assert r.status_code == 200
        assert r.json()["item"]["status"] == "dismissed"

    def test_delete_alert(self, client):
        alert = self._seed_alert(client)
        assert client.delete(f"/api/alerts/{alert['id']}").status_code == 200
        assert client.get(f"/api/alerts/{alert['id']}").status_code == 404


class TestEvaluateEndpoint:
    def test_evaluate_matching_hotspot(self, client):
        """验收 1: 手动评估匹配的热点 → 触发告警."""
        client.post("/api/alerts/rules", json=_rule_payload())
        _insert_hotspot("h-eval-1")
        from backend.repository.tags_repo import TagRepository
        TagRepository().add("fastapi", "FastAPI", "framework")
        TagRepository().attach("h-eval-1", "fastapi", 0.8)

        r = client.post("/api/alerts/evaluate/h-eval-1")
        assert r.status_code == 200
        data = r.json()
        assert data["hotspot_id"] == "h-eval-1"
        assert len(data["fired_rules"]) == 1

    def test_evaluate_no_matching_rule(self, client):
        _insert_hotspot("h-eval-2", "普通文章", "无标签")
        client.post("/api/alerts/rules", json=_rule_payload())
        r = client.post("/api/alerts/evaluate/h-eval-2")
        assert r.status_code == 200
        assert r.json()["fired_rules"] == []

    def test_evaluate_missing_hotspot(self, client):
        r = client.post("/api/alerts/evaluate/no-such-hotspot")
        assert r.status_code == 200
        assert r.json()["fired_rules"] == []

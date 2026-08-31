"""v0.7 Batch ⑤ + 设置画像 — Feedback API 端到端测试.

覆盖:
- POST /api/feedback/ — 提交 like/dislike
- GET  /api/feedback/profile — 画像摘要
- GET  /api/feedback/history — 全量反馈历史 (设置页)
- GET  /api/feedback/role-summary — 角色倾向总结 (设置页)
- GET  /api/feedback/entity/{type}/{id} — 实体反馈历史
- 校验: 非法 action 400, 非法 entity_type 400
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
    test_db = tmp_path / "test_feedback_api.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # v0.7 Batch ⑤: feedback API 注册在 secnews 扩展 gate 下
    # conftest.py 已通过 HOTSPOT_FEATURE_GATES 全开扩展, 无需额外 monkeypatch
    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)
    register_exception_handlers(app)
    register_routers(app)
    return TestClient(app)


def _insert_hotspot(hotspot_id: str, title: str = "Test", category: str = "ai", source: str = "test"):
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    from backend.repository.db import get_connection
    get_connection().execute(
        """
        INSERT OR REPLACE INTO hotspots
            (id, title, summary, source, url, category, published_at, score,
             fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hotspot_id, title, "summary", source,
            f"https://example.com/{hotspot_id}", category, now, 50.0,
            now, 0, 80, "[]", "pending", now,
        ),
    )


class TestPostFeedback:
    def test_like_returns_200(self, client):
        _insert_hotspot("h-1")
        r = client.post("/api/feedback/", json={"entity_type": "hotspot", "entity_id": "h-1", "action": "like"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["action"] == "like"
        assert data["signal"] > 0
        assert data["event_id"] is not None

    def test_dislike_returns_200(self, client):
        _insert_hotspot("h-1")
        r = client.post("/api/feedback/", json={"entity_type": "hotspot", "entity_id": "h-1", "action": "dislike"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["action"] == "dislike"
        assert data["signal"] < 0

    def test_invalid_action_returns_400(self, client):
        r = client.post("/api/feedback/", json={"entity_type": "hotspot", "entity_id": "h-1", "action": "neutral"})
        assert r.status_code == 400

    def test_missing_entity_still_accepted(self, client):
        r = client.post("/api/feedback/", json={"entity_type": "hotspot", "entity_id": "ghost", "action": "like"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["weights"] == {}


class TestGetFeedbackProfile:
    def test_empty_profile(self, client):
        r = client.get("/api/feedback/profile")
        assert r.status_code == 200
        data = r.json()
        assert "total_likes" in data
        assert "total_dislikes" in data
        assert "recent" in data

    def test_profile_after_feedback(self, client):
        _insert_hotspot("h-1")
        client.post("/api/feedback/", json={"entity_type": "hotspot", "entity_id": "h-1", "action": "like"})
        r = client.get("/api/feedback/profile")
        assert r.status_code == 200
        data = r.json()
        assert data["total_likes"] >= 1


class TestGetEntityFeedback:
    def test_entity_history(self, client):
        _insert_hotspot("h-1")
        client.post("/api/feedback/", json={"entity_type": "hotspot", "entity_id": "h-1", "action": "like"})
        client.post("/api/feedback/", json={"entity_type": "hotspot", "entity_id": "h-1", "action": "dislike"})
        r = client.get("/api/feedback/entity/hotspot/h-1")
        assert r.status_code == 200
        data = r.json()
        assert data["entity_id"] == "h-1"
        assert len(data["items"]) == 2

    def test_invalid_entity_type_400(self, client):
        r = client.get("/api/feedback/entity/invalid/h-1")
        assert r.status_code == 400

    def test_nonexistent_entity_empty(self, client):
        r = client.get("/api/feedback/entity/hotspot/ghost")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []


class TestFeedbackHistory:
    def test_history_returns_list(self, client):
        _insert_hotspot("h-1")
        client.post("/api/feedback/", json={"entity_type": "hotspot", "entity_id": "h-1", "action": "like"})
        r = client.get("/api/feedback/history?limit=10")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert len(data["items"]) >= 1

    def test_history_empty_when_no_feedback(self, client):
        r = client.get("/api/feedback/history")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []


class TestRoleSummary:
    def test_role_summary_no_feedback(self, client):
        r = client.get("/api/feedback/role-summary")
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "interests" in data
        assert "reading_style" in data
        assert data["confidence"] == 0.0

    def test_role_summary_after_feedback(self, client):
        _insert_hotspot("h-1", category="ai", source="test")
        client.post("/api/feedback/", json={"entity_type": "hotspot", "entity_id": "h-1", "action": "like"})
        r = client.get("/api/feedback/role-summary")
        assert r.status_code == 200
        data = r.json()
        assert data["total_feedback"] >= 1
        assert "累计反馈" in data["summary"]

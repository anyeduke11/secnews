"""v1.7 Phase 2 — Reviews API 端到端测试。

覆盖:
- POST /api/reviews/{type}/{id}        创建复习记录
- POST /api/reviews/{type}/{id}/grade  评分 (SM-2 推进)
- GET  /api/reviews/due                到期队列
- GET  /api/reviews/{type}/{id}        查看状态 (404 校验)
- GET  /api/reviews/stats              统计
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
    test_db = tmp_path / "test_reviews_api.db"
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


class TestReviewsCreate:
    def test_create_review(self, client):
        r = client.post("/api/reviews/concept/c-1", params={"interval_days": 0})
        assert r.status_code == 201
        item = r.json()["item"]
        assert item["entity_type"] == "concept"
        assert item["entity_id"] == "c-1"
        assert item["easiness"] == 2.5

    def test_create_idempotent(self, client):
        client.post("/api/reviews/concept/c-2", params={"interval_days": 0})
        # 评分一次
        client.post("/api/reviews/concept/c-2/grade", json={"grade": 5})
        # 再次 create 不应覆盖评分
        r = client.post("/api/reviews/concept/c-2", params={"interval_days": 0})
        assert r.status_code == 201
        assert r.json()["item"]["repetitions"] == 1  # 保留评分结果


class TestReviewsGrade:
    def test_grade_returns_ok(self, client):
        r = client.post("/api/reviews/concept/c-3/grade", json={"grade": 4})
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["item"]["last_grade"] == 4

    def test_grade_extends_interval(self, client):
        """验收 2: 评分后间隔按 SM-2 延长。"""
        r1 = client.post("/api/reviews/concept/c-4/grade", json={"grade": 4})
        i1 = r1.json()["item"]["interval"]
        r2 = client.post("/api/reviews/concept/c-4/grade", json={"grade": 4})
        i2 = r2.json()["item"]["interval"]
        assert i2 > i1

    def test_grade_invalid_rejected(self, client):
        r = client.post("/api/reviews/concept/c-5/grade", json={"grade": 6})
        assert r.status_code == 422  # pydantic Field(ge=0, le=5)


class TestReviewsDue:
    def test_due_returns_due_items(self, client):
        client.post("/api/reviews/concept/due-1", params={"interval_days": 0})
        r = client.get("/api/reviews/due")
        assert r.status_code == 200
        ids = {(it["entity_type"], it["entity_id"]) for it in r.json()["items"]}
        assert ("concept", "due-1") in ids


class TestReviewsGet:
    def test_get_existing(self, client):
        client.post("/api/reviews/concept/c-6/grade", json={"grade": 5})
        r = client.get("/api/reviews/concept/c-6")
        assert r.status_code == 200
        assert r.json()["item"]["entity_id"] == "c-6"

    def test_get_missing_404(self, client):
        r = client.get("/api/reviews/concept/no-such")
        assert r.status_code == 404


class TestReviewsStats:
    def test_stats(self, client):
        client.post("/api/reviews/concept/s-1", params={"interval_days": 0})
        client.post("/api/reviews/concept/s-2", params={"interval_days": 0})
        r = client.get("/api/reviews/stats")
        assert r.status_code == 200
        s = r.json()["stats"]
        assert s["total"] >= 2
        assert s["due"] >= 2

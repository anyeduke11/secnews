"""v1.7 Phase 2 — TechStack API 端到端测试.

覆盖:
- GET    /api/tech-stack                 列表 (+ category 过滤)
- POST   /api/tech-stack                 新建
- GET    /api/tech-stack/{id}            查看 (含 404)
- PUT    /api/tech-stack/{id}            更新 (含 404)
- DELETE /api/tech-stack/{id}            删除 (含 404)
- GET    /api/tech-stack/impact          影响分析桥接
- 校验: proficiency 越界 / 空名 / 不存在 404
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
    test_db = tmp_path / "test_tech_stack_api.db"
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


def _create_payload(
    id: str = "ts-fastapi",
    name: str = "FastAPI",
    category: str = "framework",
    proficiency: int = 3,
    notes: str = "async web framework",
) -> dict:
    return {"id": id, "name": name, "category": category, "proficiency": proficiency, "notes": notes}


class TestTechStackCreate:
    def test_create_returns_201(self, client):
        r = client.post("/api/tech-stack", json=_create_payload())
        assert r.status_code == 201
        item = r.json()["item"]
        assert item["id"] == "ts-fastapi"
        assert item["name"] == "FastAPI"
        assert item["category"] == "framework"
        assert item["proficiency"] == 3
        assert item["notes"] == "async web framework"

    def test_create_invalid_proficiency_rejected(self, client):
        # proficiency > 5 → 422
        r = client.post("/api/tech-stack", json=_create_payload(proficiency=10))
        assert r.status_code == 422
        # proficiency < 1 → 422
        r2 = client.post("/api/tech-stack", json=_create_payload(proficiency=0))
        assert r2.status_code == 422

    def test_create_empty_name_rejected(self, client):
        r = client.post("/api/tech-stack", json=_create_payload(name=""))
        assert r.status_code == 422


class TestTechStackList:
    def test_list_all(self, client):
        client.post("/api/tech-stack", json=_create_payload("ts-fa", "FastAPI", "framework"))
        client.post("/api/tech-stack", json=_create_payload("ts-react", "React", "framework"))
        client.post("/api/tech-stack", json=_create_payload("ts-py", "Python", "language"))
        r = client.get("/api/tech-stack")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 3
        assert len(data["items"]) == 3

    def test_list_by_category(self, client):
        client.post("/api/tech-stack", json=_create_payload("ts-fa", "FastAPI", "framework"))
        client.post("/api/tech-stack", json=_create_payload("ts-py", "Python", "language"))
        r = client.get("/api/tech-stack", params={"category": "framework"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["category"] == "framework"

    def test_list_empty(self, client):
        r = client.get("/api/tech-stack")
        assert r.status_code == 200
        assert r.json()["count"] == 0


class TestTechStackGetUpdateDelete:
    def test_get_existing(self, client):
        client.post("/api/tech-stack", json=_create_payload())
        r = client.get("/api/tech-stack/ts-fastapi")
        assert r.status_code == 200
        assert r.json()["item"]["name"] == "FastAPI"

    def test_get_missing_404(self, client):
        r = client.get("/api/tech-stack/no-such")
        assert r.status_code == 404

    def test_update_content(self, client):
        client.post("/api/tech-stack", json=_create_payload())
        r = client.put(
            "/api/tech-stack/ts-fastapi",
            json={"name": "FastAPI Framework", "proficiency": 4},
        )
        assert r.status_code == 200
        item = r.json()["item"]
        assert item["name"] == "FastAPI Framework"
        assert item["proficiency"] == 4
        # 未传字段保留原值
        assert item["category"] == "framework"

    def test_update_missing_404(self, client):
        r = client.put("/api/tech-stack/no-such", json={"name": "X"})
        assert r.status_code == 404

    def test_delete(self, client):
        client.post("/api/tech-stack", json=_create_payload())
        r = client.delete("/api/tech-stack/ts-fastapi")
        assert r.status_code == 200
        # 再查应 404
        assert client.get("/api/tech-stack/ts-fastapi").status_code == 404

    def test_delete_missing_404(self, client):
        r = client.delete("/api/tech-stack/no-such")
        assert r.status_code == 404


class TestTechStackImpact:
    """影响分析端点 (验收 4 的 API 层覆盖)."""

    def test_impact_missing_article_returns_empty(self, client):
        """不存在的 article_id → 空结果 (不报错)."""
        r = client.get("/api/tech-stack/impact", params={"article_id": "no-such"})
        assert r.status_code == 200
        data = r.json()
        assert data["article_id"] == "no-such"
        assert data["projects"] == []
        assert data["tags"] == []

    def test_impact_missing_param_rejected(self, client):
        """缺 article_id 参数 → 422."""
        r = client.get("/api/tech-stack/impact")
        assert r.status_code == 422

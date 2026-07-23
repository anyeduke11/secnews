"""v1.7 Phase 2 — Annotations API 端到端测试 (验收 3: 笔记 CRUD)。

覆盖:
- POST   /api/annotations          新建
- GET    /api/annotations          列表 (按 entity_type+entity_id)
- GET    /api/annotations/{id}     查看
- PUT    /api/annotations/{id}     更新
- DELETE /api/annotations/{id}     删除
- 校验: 空内容 / 不存在 404
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
    test_db = tmp_path / "test_annotations_api.db"
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


def _create_payload(content: str = "my note", entity_id: str = "k-1") -> dict:
    return {
        "entity_type": "knowledge",
        "entity_id": entity_id,
        "content": content,
        "range_start": 0,
        "range_end": 10,
    }


class TestAnnotationCreate:
    def test_create_returns_item(self, client):
        r = client.post("/api/annotations", json=_create_payload())
        assert r.status_code == 201
        item = r.json()["item"]
        assert item["content"] == "my note"
        assert item["entity_type"] == "knowledge"
        assert item["entity_id"] == "k-1"
        assert item["range_start"] == 0

    def test_create_empty_content_rejected(self, client):
        r = client.post(
            "/api/annotations",
            json=_create_payload(content=""),
        )
        assert r.status_code == 422  # pydantic min_length=1


class TestAnnotationList:
    def test_list_by_entity(self, client):
        client.post("/api/annotations", json=_create_payload("note A", "k-list"))
        client.post("/api/annotations", json=_create_payload("note B", "k-list"))
        client.post("/api/annotations", json=_create_payload("note C", "other-id"))
        r = client.get(
            "/api/annotations",
            params={"entity_type": "knowledge", "entity_id": "k-list"},
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        contents = {it["content"] for it in items}
        assert contents == {"note A", "note B"}

    def test_list_empty(self, client):
        r = client.get(
            "/api/annotations",
            params={"entity_type": "knowledge", "entity_id": "none"},
        )
        assert r.status_code == 200
        assert r.json()["count"] == 0


class TestAnnotationGetUpdateDelete:
    def test_get_existing(self, client):
        create = client.post("/api/annotations", json=_create_payload()).json()["item"]
        r = client.get(f"/api/annotations/{create['id']}")
        assert r.status_code == 200
        assert r.json()["item"]["id"] == create["id"]

    def test_get_missing_404(self, client):
        r = client.get("/api/annotations/no-such-id")
        assert r.status_code == 404

    def test_update_content(self, client):
        create = client.post("/api/annotations", json=_create_payload()).json()["item"]
        r = client.put(
            f"/api/annotations/{create['id']}",
            json={"content": "updated note"},
        )
        assert r.status_code == 200
        assert r.json()["item"]["content"] == "updated note"

    def test_update_missing_404(self, client):
        r = client.put("/api/annotations/no-such", json={"content": "x"})
        assert r.status_code == 404

    def test_delete(self, client):
        create = client.post("/api/annotations", json=_create_payload()).json()["item"]
        r = client.delete(f"/api/annotations/{create['id']}")
        assert r.status_code == 200
        # 再查应 404
        assert client.get(f"/api/annotations/{create['id']}").status_code == 404

    def test_delete_missing_404(self, client):
        r = client.delete("/api/annotations/no-such")
        assert r.status_code == 404


class TestAnnotationCRUDFlow:
    """验收 3: 笔记 CRUD 全流程。"""

    def test_full_crud_cycle(self, client):
        # Create
        create = client.post(
            "/api/annotations",
            json=_create_payload("original", "k-crud"),
        ).json()["item"]
        aid = create["id"]
        # Read
        assert client.get(f"/api/annotations/{aid}").json()["item"]["content"] == "original"
        # Update
        client.put(f"/api/annotations/{aid}", json={"content": "edited"})
        assert client.get(f"/api/annotations/{aid}").json()["item"]["content"] == "edited"
        # Delete
        assert client.delete(f"/api/annotations/{aid}").status_code == 200
        assert client.get(f"/api/annotations/{aid}").status_code == 404

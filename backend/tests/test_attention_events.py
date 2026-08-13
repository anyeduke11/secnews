"""Phase 17 — Attention Events API 端到端测试。

覆盖 (5 用例):
  - POST /api/attention/events 有效数据 → 201
  - POST /api/attention/events 非法 event_type → 400
  - POST /api/attention/events 全部 6 种 event_type
  - POST /api/attention/events 带 detail_json
  - 事件正确持久化到数据库
"""
from __future__ import annotations

import json
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
    test_db = tmp_path / "test_attention_events.db"
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


def _insert_knowledge_item(item_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = db.get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO knowledge_items
            (id, title, source, domain, topic, type, difficulty, tags, concepts,
             mastery, compiled, ingested_at, updated_at, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (item_id, f"Item {item_id}", "test", "security", "", "article", "beginner",
         "[]", "[]", 0, 0, now, now, f"https://example.com/{item_id}"),
    )


# ===========================================================================
# 1. POST /api/attention/events — 基本
# ===========================================================================
class TestCreateAttentionEvent:
    def test_valid_event_returns_201(self, client):
        _insert_knowledge_item("k-1")
        resp = client.post(
            "/api/attention/events",
            json={"item_id": "k-1", "event_type": "view"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["event_id"], int)
        assert data["event_id"] > 0

    def test_invalid_event_type_returns_400(self, client):
        _insert_knowledge_item("k-1")
        resp = client.post(
            "/api/attention/events",
            json={"item_id": "k-1", "event_type": "invalid_type"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        if isinstance(detail, dict):
            assert "event_type" in detail["message"]
        else:
            assert "event_type" in detail

    def test_all_six_event_types_accepted(self, client):
        _insert_knowledge_item("k-all")
        valid_types = ["view", "dwell", "scroll", "favorite", "annotation", "share"]
        for et in valid_types:
            resp = client.post(
                "/api/attention/events",
                json={"item_id": "k-all", "event_type": et},
            )
            assert resp.status_code == 201, f"Failed for event_type={et!r}"
            data = resp.json()
            assert data["success"] is True

    def test_with_detail_json(self, client):
        _insert_knowledge_item("k-detail")
        resp = client.post(
            "/api/attention/events",
            json={
                "item_id": "k-detail",
                "event_type": "dwell",
                "detail_json": {"dwell_seconds": 42, "page": "test"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True

        # Verify detail_json was persisted correctly
        conn = db.get_connection()
        row = conn.execute(
            "SELECT detail_json FROM attention_events WHERE id = ?",
            (data["event_id"],),
        ).fetchone()
        assert row is not None
        detail = json.loads(row["detail_json"])
        assert detail["dwell_seconds"] == 42
        assert detail["page"] == "test"

    def test_event_is_persisted_in_database(self, client):
        _insert_knowledge_item("k-persist")
        resp = client.post(
            "/api/attention/events",
            json={"item_id": "k-persist", "event_type": "view"},
        )
        assert resp.status_code == 201
        event_id = resp.json()["event_id"]

        # Direct DB query to verify persistence
        conn = db.get_connection()
        row = conn.execute(
            "SELECT id, item_id, event_type, detail_json, created_at "
            "FROM attention_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        assert row is not None
        assert row["item_id"] == "k-persist"
        assert row["event_type"] == "view"
        # created_at should be a valid ISO timestamp
        assert datetime.fromisoformat(row["created_at"]) is not None
"""v1.7 Phase 3 — Unified Search API 端到端测试.

覆盖:
- GET /api/search?q=... 基础搜索
- sources 参数过滤 (hotspot, knowledge, 逗号分隔)
- limit 参数
- 空查询
- 无结果
- limit 越界 (422)
- 跨层结果
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
    test_db = tmp_path / "test_search_api.db"
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


def _insert_hotspot(hid: str, title: str, summary: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    from backend.repository.db import get_connection
    get_connection().execute(
        """
        INSERT OR REPLACE INTO hotspots
            (id, title, summary, source, url, category, published_at, score,
             fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (hid, title, summary, "test", f"https://example.com/{hid}",
         "security", now, 50.0, now, 0, 80, "[]", "pending", now),
    )


def _insert_knowledge(kid: str, title: str, topic: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    from backend.repository.db import get_connection
    get_connection().execute(
        """
        INSERT OR REPLACE INTO knowledge_items
            (id, title, source, domain, topic, type, difficulty, tags, concepts,
             mastery, compiled, ingested_at, updated_at, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (kid, title, "test", "security", topic, "article", "beginner",
         "[]", "[]", 0, 0, now, now, f"https://example.com/{kid}"),
    )


class TestBasicSearch:
    def test_returns_version_envelope(self, client):
        r = client.get("/api/search", params={"q": "test"})
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == "1.7.0"
        assert "result" in body

    def test_hotspot_match(self, client):
        _insert_hotspot("h1", "FastAPI 漏洞", "RCE 风险")
        r = client.get("/api/search", params={"q": "FastAPI"})
        assert r.status_code == 200
        items = r.json()["result"]["items"]
        assert len(items) == 1
        assert items[0]["entity_type"] == "hotspot"
        assert items[0]["entity_id"] == "h1"

    def test_knowledge_match(self, client):
        _insert_knowledge("k1", "FastAPI 教程", "Web 框架")
        r = client.get("/api/search", params={"q": "FastAPI"})
        items = r.json()["result"]["items"]
        assert len(items) == 1
        assert items[0]["entity_type"] == "knowledge"

    def test_cross_layer_match(self, client):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        r = client.get("/api/search", params={"q": "FastAPI"})
        items = r.json()["result"]["items"]
        assert len(items) == 2
        types = {i["entity_type"] for i in items}
        assert types == {"hotspot", "knowledge"}


class TestSourceFilter:
    def test_hotspot_only(self, client):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        r = client.get("/api/search", params={"q": "FastAPI", "sources": "hotspot"})
        items = r.json()["result"]["items"]
        assert len(items) == 1
        assert items[0]["entity_type"] == "hotspot"

    def test_knowledge_only(self, client):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        r = client.get("/api/search", params={"q": "FastAPI", "sources": "knowledge"})
        items = r.json()["result"]["items"]
        assert len(items) == 1
        assert items[0]["entity_type"] == "knowledge"

    def test_multiple_sources_comma_separated(self, client):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        r = client.get("/api/search", params={"q": "FastAPI", "sources": "hotspot,knowledge"})
        items = r.json()["result"]["items"]
        assert len(items) == 2


class TestLimit:
    def test_limit_param(self, client):
        for i in range(5):
            _insert_hotspot(f"h{i}", f"FastAPI 第{i}篇", "")
        r = client.get("/api/search", params={"q": "FastAPI", "limit": 3})
        items = r.json()["result"]["items"]
        assert len(items) == 3

    def test_limit_above_max_rejected(self, client):
        r = client.get("/api/search", params={"q": "test", "limit": 200})
        assert r.status_code == 422  # le=100

    def test_limit_zero_rejected(self, client):
        r = client.get("/api/search", params={"q": "test", "limit": 0})
        assert r.status_code == 422  # ge=1


class TestEdgeCases:
    def test_empty_query_returns_empty(self, client):
        _insert_hotspot("h1", "FastAPI", "")
        r = client.get("/api/search", params={"q": ""})
        items = r.json()["result"]["items"]
        assert items == []

    def test_no_match_returns_empty(self, client):
        _insert_hotspot("h1", "FastAPI", "")
        r = client.get("/api/search", params={"q": "不存在XYZ"})
        items = r.json()["result"]["items"]
        assert items == []

    def test_default_limit_applied(self, client):
        for i in range(25):
            _insert_hotspot(f"h{i}", f"FastAPI 第{i}篇", "")
        r = client.get("/api/search", params={"q": "FastAPI"})
        items = r.json()["result"]["items"]
        assert len(items) == 20  # 默认 limit=20


class TestGroupedStructure:
    def test_grouped_in_response(self, client):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        r = client.get("/api/search", params={"q": "FastAPI"})
        grouped = r.json()["result"]["grouped"]
        assert "hotspot" in grouped
        assert "knowledge" in grouped
        assert len(grouped["hotspot"]) == 1
        assert len(grouped["knowledge"]) == 1

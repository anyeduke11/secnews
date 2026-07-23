"""v1.7 Phase 1 — Tags API 端到端测试。

覆盖:
- GET /api/tags (列表 + type/parent_id 筛选)
- GET /api/tags/suggest (前缀搜索)
- POST /api/tags (新建)
- DELETE /api/tags/{id} (删除 + 404)
- GET /api/tags/by-hotspot/{hotspot_id} (热点标签)
- 种子标签 (迁移 035 注入的 14 个) 可读
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api.middleware import TraceIDMiddleware
from backend.config import config
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.exceptions import register_exception_handlers
from backend.repository import db
from backend.repository.hotspot_repo import HotspotRepository


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_tags_api.db"
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


def _make_hotspot(hid: str, title: str = "Test") -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=hid,
        title=title,
        source="test",
        url=f"https://example.com/{hid}",
        category=Category.AI,
        published_at=now - timedelta(hours=1),
        fetched_at=now,
        quality_flags=[],
    )


# ===========================================================================
# 1. 列表 + 种子标签
# ===========================================================================
class TestTagsList:
    def test_list_returns_seed_tags(self, client):
        """迁移 035 注入 14 个种子标签, 列表应包含它们。"""
        r = client.get("/api/tags")
        assert r.status_code == 200
        body = r.json()
        ids = {t["id"] for t in body["items"]}
        # 种子标签子集校验
        for seed in ("cve", "vulnerability", "ai-security", "llm"):
            assert seed in ids, f"seed tag {seed} missing"

    def test_list_filter_by_type(self, client):
        r = client.get("/api/tags", params={"type": "cve"})
        assert r.status_code == 200
        for t in r.json()["items"]:
            assert t["type"] == "cve"

    def test_list_limit_param(self, client):
        r = client.get("/api/tags", params={"limit": 3})
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 3


# ===========================================================================
# 2. suggest
# ===========================================================================
class TestTagsSuggest:
    def test_suggest_by_prefix(self, client):
        r = client.get("/api/tags/suggest", params={"q": "cv"})
        assert r.status_code == 200
        ids = {t["id"] for t in r.json()["items"]}
        assert "cve" in ids

    def test_suggest_no_match(self, client):
        r = client.get("/api/tags/suggest", params={"q": "zzzznotexist"})
        assert r.status_code == 200
        assert r.json()["count"] == 0


# ===========================================================================
# 3. create + delete
# ===========================================================================
class TestTagsCreateDelete:
    def test_create_and_get(self, client):
        r = client.post(
            "/api/tags",
            json={"id": "mytag", "label": "My Tag", "type": "domain"},
        )
        assert r.status_code == 201
        assert r.json()["item"]["id"] == "mytag"

        # 列表能查到
        r2 = client.get("/api/tags", params={"type": "domain"})
        ids = {t["id"] for t in r2.json()["items"]}
        assert "mytag" in ids

    def test_create_invalid_type_rejected(self, client):
        r = client.post(
            "/api/tags",
            json={"id": "bad", "label": "Bad", "type": "not-a-real-type"},
        )
        assert r.status_code == 422  # pydantic pattern validation

    def test_delete_existing(self, client):
        client.post(
            "/api/tags",
            json={"id": "deltag", "label": "Del", "type": "framework"},
        )
        r = client.delete("/api/tags/deltag")
        assert r.status_code == 200
        assert r.json()["deleted"] == "deltag"

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/tags/no-such-tag")
        assert r.status_code == 404


# ===========================================================================
# 4. by-hotspot
# ===========================================================================
class TestTagsByHotspot:
    def test_by_hotspot_returns_attached_tags(self, client, temp_db):
        # 先建热点 (FK 约束需要热点存在)
        HotspotRepository().upsert_many([_make_hotspot("h-t1", "CVE-2024-1234 demo")])
        # 触发提取 (extract API 会 attach 标签)
        r = client.post("/api/extract/hotspot/h-t1")
        assert r.status_code == 200
        assert len(r.json()["attached"]) > 0

        # 查询热点标签
        r2 = client.get("/api/tags/by-hotspot/h-t1")
        assert r2.status_code == 200
        assert r2.json()["count"] > 0
        ids = {t["id"] for t in r2.json()["items"]}
        assert "cve" in ids  # "CVE-2024 demo" 应命中 cve 正则

    def test_by_hotspot_no_tags(self, client, temp_db):
        HotspotRepository().upsert_many([_make_hotspot("h-empty", "no tags here")])
        r = client.get("/api/tags/by-hotspot/h-empty")
        assert r.status_code == 200
        # 没有提取过, 应为 0 (除非关键词命中)
        assert isinstance(r.json()["items"], list)

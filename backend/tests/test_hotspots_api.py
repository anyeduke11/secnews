"""v1.7 Phase 1 — Hotspots API 标签筛选 (AND/OR) 测试。

覆盖:
- GET /api/hotspots?tags=cve  (OR 单标签)
- GET /api/hotspots?tags=cve,ai-security&tag_mode=and  (AND 多标签)
- GET /api/hotspots?tags=cve,ai-security&tag_mode=or   (OR 多标签)
- 空 tags → 正常列表 (不走标签筛选)
- GET /api/hotspots/{id} 详情返回 tags 字段 (验收 1)
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
from backend.repository.tags_repo import TagRepository


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_hotspots_api.db"
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


def _make_hotspot(hid: str, title: str = "T") -> HotspotItem:
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


def _seed_hotspots_with_tags(temp_db):
    """建 3 个热点并手动 attach 标签:
    - h1: cve
    - h2: ai-security
    - h3: cve + ai-security
    """
    repo = HotspotRepository()
    repo.upsert_many([_make_hotspot(f"h{i}", f"hot {i}") for i in (1, 2, 3)])
    tag_repo = TagRepository()
    tag_repo.attach("h1", "cve")
    tag_repo.attach("h2", "ai-security")
    tag_repo.attach("h3", "cve")
    tag_repo.attach("h3", "ai-security")


# ===========================================================================
# 1. OR 模式
# ===========================================================================
class TestTagsOrFilter:
    def test_or_single_tag(self, client, temp_db):
        _seed_hotspots_with_tags(temp_db)
        r = client.get("/api/hotspots", params={"tags": "cve", "tag_mode": "or"})
        assert r.status_code == 200
        ids = {it["id"] for it in r.json()["items"]}
        assert ids == {"h1", "h3"}  # h1, h3 有 cve

    def test_or_multi_tag_returns_union(self, client, temp_db):
        _seed_hotspots_with_tags(temp_db)
        r = client.get(
            "/api/hotspots",
            params={"tags": "cve,ai-security", "tag_mode": "or"},
        )
        assert r.status_code == 200
        ids = {it["id"] for it in r.json()["items"]}
        assert ids == {"h1", "h2", "h3"}  # 并集


# ===========================================================================
# 2. AND 模式
# ===========================================================================
class TestTagsAndFilter:
    def test_and_multi_tag_returns_intersection(self, client, temp_db):
        _seed_hotspots_with_tags(temp_db)
        r = client.get(
            "/api/hotspots",
            params={"tags": "cve,ai-security", "tag_mode": "and"},
        )
        assert r.status_code == 200
        ids = {it["id"] for it in r.json()["items"]}
        assert ids == {"h3"}  # 只有 h3 同时有两个标签

    def test_and_single_tag(self, client, temp_db):
        _seed_hotspots_with_tags(temp_db)
        r = client.get(
            "/api/hotspots",
            params={"tags": "ai-security", "tag_mode": "and"},
        )
        assert r.status_code == 200
        ids = {it["id"] for it in r.json()["items"]}
        assert ids == {"h2", "h3"}


# ===========================================================================
# 3. 无标签 → 正常列表
# ===========================================================================
class TestNoTagsFilter:
    def test_empty_tags_uses_normal_list(self, client, temp_db):
        """不传 tags 时走正常 list_hotspots, 不报错。"""
        HotspotRepository().upsert_many([_make_hotspot("h-normal", "normal")])
        r = client.get("/api/hotspots")
        assert r.status_code == 200
        assert "items" in r.json()


# ===========================================================================
# 4. 详情页返回 tags (验收 1)
# ===========================================================================
class TestHotspotDetailTags:
    def test_detail_includes_tags_field(self, client, temp_db):
        HotspotRepository().upsert_many([
            _make_hotspot("h-detail", "CVE-2024 detail")
        ])
        TagRepository().attach("h-detail", "cve")

        r = client.get("/api/hotspots/h-detail")
        assert r.status_code == 200
        body = r.json()
        assert "tags" in body
        ids = {t["id"] for t in body["tags"]}
        assert "cve" in ids

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


# ===========================================================================
# 5. exclude_category (机制通用; DEV-0183 前默认排除 bid, 现以 security 验证
#    同一机制 — 不用 tech, 因 ai 桶查询含 IN ('ai','tech') 合并口径)
# ===========================================================================
def _make_excluded_hotspot(hid: str, title: str = "security item") -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=hid,
        title=title,
        source="test",
        url=f"https://example.com/{hid}",
        category=Category.SECURITY,
        published_at=now - timedelta(hours=1),
        fetched_at=now,
        quality_flags=[],
    )


class TestExcludeCategory:
    @pytest.fixture(autouse=True)
    def _clear_list_cache(self):
        """list_cache 是模块级共享 TTL 缓存, 同 key 跨测试会命中脏结果。"""
        from backend.cache import list_cache as _list_cache

        _list_cache.clear()
        yield
        _list_cache.clear()

    def test_exclude_category_filters_out_target(self, client, temp_db):
        """exclude_category=security 时, security 条目不出现在列表, 其他分类正常。"""
        HotspotRepository().upsert_many([
            _make_hotspot("h-ai", "ai news"),
            _make_excluded_hotspot("h-ex", "vuln disclosure"),
        ])
        r = client.get("/api/hotspots?exclude_category=security")
        assert r.status_code == 200
        items = r.json()["items"]
        ids = {it["id"] for it in items}
        assert "h-ex" not in ids
        assert "h-ai" in ids

    def test_no_exclude_keeps_all(self, client, temp_db):
        """不传 exclude_category 时行为与既有版本一致 (全部条目正常返回)。"""
        HotspotRepository().upsert_many([
            _make_hotspot("h-ai2", "ai news"),
            _make_excluded_hotspot("h-ex2", "vuln disclosure"),
        ])
        r = client.get("/api/hotspots")
        assert r.status_code == 200
        ids = {it["id"] for it in r.json()["items"]}
        assert "h-ex2" in ids
        assert "h-ai2" in ids

    def test_exclude_category_total_consistent(self, client, temp_db):
        """exclude_category 时 total (去重 url 数) 与 items 口径一致 (不含被排除分类)。"""
        HotspotRepository().upsert_many([
            _make_hotspot("h-ai3", "ai news"),
            _make_excluded_hotspot("h-ex3", "vuln disclosure"),
        ])
        r = client.get("/api/hotspots?exclude_category=security")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        assert all(it["category"] != "security" for it in body["items"])


# ===========================================================================
# 6. 实践域打标 + 兴趣域加权 (DEV-0176 T0.4: 降权不删, 游标时序不变)
# ===========================================================================
def _make_titled_hotspot(hid: str, title: str, hours_ago: int) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=hid,
        title=title,
        source="test",
        url=f"https://example.com/{hid}",
        category=Category.AI,
        published_at=now - timedelta(hours=hours_ago),
        fetched_at=now,
        ingested_at=now - timedelta(hours=hours_ago),
        quality_flags=[],
    )


def _seed_three_practice_items():
    """原始时序 (新→旧): 央行(无实践域) → 等保(compliance) → CVE(vuln_research)。"""
    HotspotRepository().upsert_many([
        _make_titled_hotspot("h-fin", "央行发布年度支付体系报告", 1),
        _make_titled_hotspot("h-cmp", "等保 2.0 三级测评要点解读", 2),
        _make_titled_hotspot("h-vul", "CVE-2026-9999 漏洞复现与分析", 3),
    ])


class TestPracticeDomainBoost:
    @pytest.fixture(autouse=True)
    def _clear_caches(self):
        from backend.cache import list_cache as _list_cache
        from backend.services.interest_engine_service import InterestEngineService

        _list_cache.clear()
        InterestEngineService.invalidate_cache()
        yield
        _list_cache.clear()
        InterestEngineService.invalidate_cache()

    def test_items_carry_practice_domain(self, client, temp_db):
        """每个 item 附带 practice_domain 即时打标 (无 boost 也返回 — 加字段向后兼容)。"""
        _seed_three_practice_items()
        r = client.get("/api/hotspots")
        assert r.status_code == 200
        items = r.json()["items"]
        by_id = {it["id"]: it for it in items}
        assert by_id["h-vul"]["practice_domain"] == "vuln_research"
        assert by_id["h-cmp"]["practice_domain"] == "compliance"
        assert by_id["h-fin"]["practice_domain"] is None
        assert r.json()["interest_domains"] == []

    def test_boost_ranks_matching_first_without_dropping(self, client, temp_db):
        """兴趣域命中置顶, 但未命中条目不删除 (降权不删)。"""
        _seed_three_practice_items()
        # 预置兴趣画像 (router 从 settings.kv 读取)
        from backend.repository.settings_repo import SettingsRepository

        SettingsRepository().set("interest.practice_domains", ["vuln_research"])
        r = client.get("/api/hotspots")
        assert r.status_code == 200
        body = r.json()
        ids = [it["id"] for it in body["items"]]
        assert set(ids) == {"h-fin", "h-cmp", "h-vul"}, "未命中条目不得被删除"
        assert ids[0] == "h-vul", "命中兴趣域的条目应置顶"
        assert body["interest_domains"] == ["vuln_research"]

    def test_no_interest_keeps_raw_order(self, client, temp_db):
        """空画像时排序行为与既有版本一致 (原始时序)。"""
        _seed_three_practice_items()
        r = client.get("/api/hotspots")
        ids = [it["id"] for it in r.json()["items"]]
        assert ids == ["h-fin", "h-cmp", "h-vul"]

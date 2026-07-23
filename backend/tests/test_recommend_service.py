"""v1.7 Phase 4 — RecommendService 测试.

覆盖:
- recommend_knowledge: 标签重叠 / 无标签 / 无候选 / 排序 / limit
- recommend_hotspot: 标签重叠 (hotspot_tags 关联表) / 无标签 / 排序
- recommend: 统一入口分发 / 非法 entity_type
- API: GET /api/recommend/{entity_type}/{entity_id}
- 验收 2: 知识推荐侧栏显示相关条目
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
from backend.services.recommend_service import (
    recommend,
    recommend_hotspot,
    recommend_knowledge,
)


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_recommend.db"
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


def _insert_knowledge(kid: str, title: str, tags: list[str], ingested_at: str = "") -> None:
    import json
    from backend.repository.knowledge_repo import knowledge_repo
    from backend.domain.knowledge_models import KnowledgeItem
    now = ingested_at or datetime.now(timezone.utc).isoformat()
    item = KnowledgeItem(
        id=kid,
        title=title,
        source="test",
        domain="security",
        topic="test",
        type="article",
        difficulty="beginner",
        tags=tags,
        concepts=[],
        mastered=0,
        lifecycle="signal",
        ingested_at=now,
        updated_at=now,
    )
    knowledge_repo.upsert_item(item)


def _insert_hotspot_with_tags(hid: str, title: str, tags: list[str]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    from backend.repository.db import get_connection
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO hotspots
           (id, title, summary, source, url, category, published_at, score,
            fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at)
           VALUES (?, ?, '', 'test', ?, 'security', ?, 50.0, ?, 0, 80, '[]', 'pending', ?)""",
        (hid, title, f"https://example.com/{hid}", now, now, now),
    )
    for tag in tags:
        tag_id = tag.lower().replace(" ", "-")
        conn.execute(
            "INSERT OR IGNORE INTO tags (id, label, type, weight, created_at) VALUES (?, ?, 'domain', 1.0, ?)",
            (tag_id, tag, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO hotspot_tags (hotspot_id, tag_id, confidence, created_at) VALUES (?, ?, 1.0, ?)",
            (hid, tag_id, now),
        )


# ---------------------------------------------------------------------------
# recommend_knowledge
# ---------------------------------------------------------------------------
class TestRecommendKnowledge:
    def test_returns_related_by_tag_overlap(self, temp_db):
        _insert_knowledge("seed", "种子文章", ["fastapi", "security"])
        _insert_knowledge("related1", "相关文章1", ["fastapi", "python"])
        _insert_knowledge("related2", "相关文章2", ["security", "vuln"])
        _insert_knowledge("unrelated", "无关文章", ["golang", "crypto"])

        results = recommend_knowledge("seed")
        ids = [r["item"]["id"] for r in results]
        assert "related1" in ids
        assert "related2" in ids
        assert "unrelated" not in ids

    def test_score_reflects_overlap_count(self, temp_db):
        _insert_knowledge("seed", "种子", ["a", "b", "c"])
        _insert_knowledge("one_match", "一标签", ["a", "x"])
        _insert_knowledge("two_match", "两标签", ["a", "b", "y"])

        results = recommend_knowledge("seed")
        # two_match (score=2) 应排在 one_match (score=1) 前
        assert results[0]["item"]["id"] == "two_match"
        assert results[0]["score"] == 2
        assert results[1]["item"]["id"] == "one_match"
        assert results[1]["score"] == 1

    def test_shared_tags_in_result(self, temp_db):
        _insert_knowledge("seed", "种子", ["fastapi", "security"])
        _insert_knowledge("related", "相关", ["fastapi", "python"])
        results = recommend_knowledge("seed")
        assert "fastapi" in results[0]["shared_tags"]

    def test_empty_when_seed_has_no_tags(self, temp_db):
        _insert_knowledge("seed", "种子", [])
        _insert_knowledge("other", "其他", ["fastapi"])
        assert recommend_knowledge("seed") == []

    def test_empty_when_seed_missing(self, temp_db):
        assert recommend_knowledge("nonexistent") == []

    def test_empty_when_no_overlap(self, temp_db):
        _insert_knowledge("seed", "种子", ["fastapi"])
        _insert_knowledge("other", "其他", ["golang"])
        assert recommend_knowledge("seed") == []

    def test_excludes_self(self, temp_db):
        _insert_knowledge("seed", "种子", ["fastapi"])
        results = recommend_knowledge("seed")
        assert all(r["item"]["id"] != "seed" for r in results)

    def test_limit(self, temp_db):
        _insert_knowledge("seed", "种子", ["shared"])
        for i in range(10):
            _insert_knowledge(f"k{i}", f"候选{i}", ["shared"])
        results = recommend_knowledge("seed", limit=3)
        assert len(results) == 3

    def test_limit_clamped_to_max(self, temp_db):
        _insert_knowledge("seed", "种子", ["shared"])
        for i in range(3):
            _insert_knowledge(f"k{i}", f"候选{i}", ["shared"])
        results = recommend_knowledge("seed", limit=100)
        assert len(results) <= 20  # _MAX_LIMIT

    def test_tie_break_by_ingested_at_desc(self, temp_db):
        """同分时按 ingested_at 降序 (更新的优先)。"""
        old = "2026-01-01T00:00:00+00:00"
        new = "2026-07-01T00:00:00+00:00"
        _insert_knowledge("seed", "种子", ["shared"])
        _insert_knowledge("old", "旧文章", ["shared"], ingested_at=old)
        _insert_knowledge("new", "新文章", ["shared"], ingested_at=new)
        results = recommend_knowledge("seed")
        # 两者 score 相同 (都=1), 新的应排前面
        assert results[0]["item"]["id"] == "new"
        assert results[1]["item"]["id"] == "old"


# ---------------------------------------------------------------------------
# recommend_hotspot
# ---------------------------------------------------------------------------
class TestRecommendHotspot:
    def test_returns_related_by_tag_overlap(self, temp_db):
        _insert_hotspot_with_tags("seed", "种子热点", ["fastapi", "security"])
        _insert_hotspot_with_tags("related", "相关热点", ["fastapi", "python"])
        _insert_hotspot_with_tags("unrelated", "无关热点", ["golang"])
        results = recommend_hotspot("seed")
        ids = [r["item"]["id"] for r in results]
        assert "related" in ids
        assert "unrelated" not in ids

    def test_empty_when_seed_has_no_tags(self, temp_db):
        # 插入无标签的 hotspot
        now = datetime.now(timezone.utc).isoformat()
        from backend.repository.db import get_connection
        get_connection().execute(
            """INSERT OR REPLACE INTO hotspots
               (id, title, summary, source, url, category, published_at, score,
                fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at)
               VALUES ('seed', '无标签', '', 'test', 'https://x.com', 'security', ?, 50.0, ?, 0, 80, '[]', 'pending', ?)""",
            (now, now, now),
        )
        _insert_hotspot_with_tags("other", "有标签", ["fastapi"])
        assert recommend_hotspot("seed") == []

    def test_empty_when_seed_missing(self, temp_db):
        assert recommend_hotspot("nonexistent") == []

    def test_excludes_self(self, temp_db):
        _insert_hotspot_with_tags("seed", "种子", ["fastapi"])
        _insert_hotspot_with_tags("other", "其他", ["fastapi"])
        results = recommend_hotspot("seed")
        assert all(r["item"]["id"] != "seed" for r in results)

    def test_score_reflects_overlap(self, temp_db):
        _insert_hotspot_with_tags("seed", "种子", ["a", "b", "c"])
        _insert_hotspot_with_tags("one", "一标签", ["a", "x"])
        _insert_hotspot_with_tags("two", "两标签", ["a", "b", "y"])
        results = recommend_hotspot("seed")
        assert results[0]["item"]["id"] == "two"
        assert results[0]["score"] >= results[1]["score"]

    def test_limit(self, temp_db):
        _insert_hotspot_with_tags("seed", "种子", ["shared"])
        for i in range(10):
            _insert_hotspot_with_tags(f"h{i}", f"热点{i}", ["shared"])
        results = recommend_hotspot("seed", limit=3)
        assert len(results) == 3


# ---------------------------------------------------------------------------
# recommend (统一入口)
# ---------------------------------------------------------------------------
class TestRecommendUnified:
    def test_dispatches_to_knowledge(self, temp_db):
        _insert_knowledge("seed", "种子", ["fastapi"])
        _insert_knowledge("related", "相关", ["fastapi"])
        results = recommend("knowledge", "seed")
        assert len(results) == 1
        assert results[0]["item"]["id"] == "related"

    def test_dispatches_to_hotspot(self, temp_db):
        _insert_hotspot_with_tags("seed", "种子", ["fastapi"])
        _insert_hotspot_with_tags("related", "相关", ["fastapi"])
        results = recommend("hotspot", "seed")
        assert len(results) == 1
        assert results[0]["item"]["id"] == "related"

    def test_invalid_entity_type_returns_empty(self, temp_db):
        assert recommend("invalid", "any") == []


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class TestRecommendAPI:
    def test_returns_version_envelope(self, client):
        r = client.get("/api/recommend/knowledge/seed")
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == "1.7.0"
        assert body["entity_type"] == "knowledge"
        assert body["entity_id"] == "seed"
        assert "items" in body

    def test_knowledge_recommendation(self, client):
        _insert_knowledge("seed", "种子", ["fastapi"])
        _insert_knowledge("related", "相关", ["fastapi"])
        r = client.get("/api/recommend/knowledge/seed")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["item"]["id"] == "related"

    def test_hotspot_recommendation(self, client):
        _insert_hotspot_with_tags("seed", "种子", ["fastapi"])
        _insert_hotspot_with_tags("related", "相关", ["fastapi"])
        r = client.get("/api/recommend/hotspot/seed")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["item"]["id"] == "related"

    def test_empty_results(self, client):
        r = client.get("/api/recommend/knowledge/nonexistent")
        assert r.json()["items"] == []

    def test_limit_param(self, client):
        _insert_knowledge("seed", "种子", ["shared"])
        for i in range(5):
            _insert_knowledge(f"k{i}", f"候选{i}", ["shared"])
        r = client.get("/api/recommend/knowledge/seed", params={"limit": 2})
        assert len(r.json()["items"]) == 2

    def test_limit_above_max_rejected(self, client):
        r = client.get("/api/recommend/knowledge/seed", params={"limit": 50})
        assert r.status_code == 422  # le=20

    def test_limit_zero_rejected(self, client):
        r = client.get("/api/recommend/knowledge/seed", params={"limit": 0})
        assert r.status_code == 422  # ge=1


# ---------------------------------------------------------------------------
# 验收 2: 知识推荐侧栏显示相关条目
# ---------------------------------------------------------------------------
class TestAcceptance2RecommendSidebar:
    """验收 2: 知识推荐侧栏显示相关条目。"""

    def test_sidebar_gets_related_items(self, temp_db):
        # 场景: 用户正在阅读一篇 FastAPI 文章
        _insert_knowledge("current", "FastAPI 性能优化", ["fastapi", "python", "performance"])
        # 知识库中有 3 篇相关文章 (共享 fastapi 标签)
        _insert_knowledge("r1", "FastAPI 中间件指南", ["fastapi", "python"])
        _insert_knowledge("r2", "FastAPI 部署实战", ["fastapi", "docker"])
        _insert_knowledge("r3", "Go 语言入门", ["golang"])  # 无关

        results = recommend_knowledge("current", limit=5)
        ids = [r["item"]["id"] for r in results]

        # 推荐侧栏应显示 r1 和 r2 (共享 fastapi 标签), 不显示 r3
        assert "r1" in ids
        assert "r2" in ids
        assert "r3" not in ids
        assert len(results) == 2

    def test_sidebar_via_api(self, client):
        _insert_knowledge("current", "FastAPI 文章", ["fastapi"])
        _insert_knowledge("related", "FastAPI 相关", ["fastapi"])

        r = client.get("/api/recommend/knowledge/current")
        items = r.json()["items"]
        assert len(items) >= 1
        assert any(i["item"]["id"] == "related" for i in items)

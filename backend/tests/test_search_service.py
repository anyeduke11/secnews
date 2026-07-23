"""v1.7 Phase 3 — Unified Search 服务层测试.

覆盖:
- 基础搜索 (title / summary 匹配)
- 大小写不敏感
- source 过滤 (hotspot only / knowledge only / both / invalid)
- limit 边界
- 空查询
- LIKE 通配符转义
- 跨层分组 (grouped)
- 便捷方法 search_hotspots_only / search_knowledge_only
- 性能预算 (10k 行 P95 < 500ms)
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.services.search_service import (
    search_hotspots_only,
    search_knowledge_only,
    unified_search,
)


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_search.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _insert_hotspot(
    hid: str,
    title: str,
    summary: str = "",
    category: str = "security",
    ingested_at: str | None = None,
) -> None:
    now = ingested_at or datetime.now(timezone.utc).isoformat()
    from backend.repository.db import get_connection
    get_connection().execute(
        """
        INSERT OR REPLACE INTO hotspots
            (id, title, summary, source, url, category, published_at, score,
             fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (hid, title, summary, "test", f"https://example.com/{hid}",
         category, now, 50.0, now, 0, 80, "[]", "pending", now),
    )


def _insert_knowledge(
    kid: str,
    title: str,
    topic: str = "",
    domain: str = "security",
    ingested_at: str | None = None,
) -> None:
    now = ingested_at or datetime.now(timezone.utc).isoformat()
    from backend.repository.db import get_connection
    get_connection().execute(
        """
        INSERT OR REPLACE INTO knowledge_items
            (id, title, source, domain, topic, type, difficulty, tags, concepts,
             mastery, compiled, ingested_at, updated_at, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (kid, title, "test", domain, topic, "article", "beginner",
         "[]", "[]", 0, 0, now, now, f"https://example.com/{kid}"),
    )


class TestBasicSearch:
    def test_title_match_hotspot(self, temp_db):
        _insert_hotspot("h1", "FastAPI 漏洞分析", "RCE 风险")
        result = unified_search("FastAPI")
        assert len(result["items"]) == 1
        assert result["items"][0]["entity_type"] == "hotspot"
        assert result["items"][0]["entity_id"] == "h1"

    def test_summary_match_hotspot(self, temp_db):
        _insert_hotspot("h1", "无关标题", "FastAPI 远程代码执行")
        result = unified_search("FastAPI")
        assert len(result["items"]) == 1
        assert result["items"][0]["entity_id"] == "h1"

    def test_title_match_knowledge(self, temp_db):
        _insert_knowledge("k1", "FastAPI 教程", "Web 框架")
        result = unified_search("FastAPI")
        assert len(result["items"]) == 1
        assert result["items"][0]["entity_type"] == "knowledge"

    def test_topic_match_knowledge(self, temp_db):
        _insert_knowledge("k1", "通用标题", "FastAPI 主题")
        result = unified_search("FastAPI")
        assert len(result["items"]) == 1

    def test_case_insensitive(self, temp_db):
        _insert_hotspot("h1", "fastapi 漏洞", "")
        # 大写查询应匹配小写标题
        assert len(unified_search("FASTAPI")["items"]) == 1
        # 混合大小写
        assert len(unified_search("FastApi")["items"]) == 1

    def test_no_match(self, temp_db):
        _insert_hotspot("h1", "FastAPI 漏洞", "")
        result = unified_search("不存在的关键词XYZ")
        assert result["items"] == []
        assert result["grouped"] == {}


class TestSourceFilter:
    def test_hotspot_only(self, temp_db):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        result = unified_search("FastAPI", sources=["hotspot"])
        assert len(result["items"]) == 1
        assert result["items"][0]["entity_type"] == "hotspot"

    def test_knowledge_only(self, temp_db):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        result = unified_search("FastAPI", sources=["knowledge"])
        assert len(result["items"]) == 1
        assert result["items"][0]["entity_type"] == "knowledge"

    def test_both_sources(self, temp_db):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        result = unified_search("FastAPI")
        assert len(result["items"]) == 2

    def test_invalid_source_dropped_keeps_valid(self, temp_db):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        # "invalid" 被丢弃, 只保留 "hotspot" → 只返回 hotspot 层
        result = unified_search("FastAPI", sources=["invalid", "hotspot"])
        assert len(result["items"]) == 1
        assert result["items"][0]["entity_type"] == "hotspot"

    def test_all_invalid_sources_means_no_filter(self, temp_db):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        # 全部非法 → effective_sources 为空 → 无过滤 → 全部返回
        result = unified_search("FastAPI", sources=["invalid1", "invalid2"])
        assert len(result["items"]) == 2

    def test_empty_sources_list_means_all(self, temp_db):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        result = unified_search("FastAPI", sources=[])
        assert len(result["items"]) == 2


class TestLimit:
    def test_limit_caps_results(self, temp_db):
        for i in range(5):
            _insert_hotspot(f"h{i}", f"FastAPI 第{i}篇", "")
        result = unified_search("FastAPI", limit=3)
        assert len(result["items"]) == 3

    def test_limit_above_max_capped(self, temp_db):
        for i in range(3):
            _insert_hotspot(f"h{i}", f"FastAPI 第{i}篇", "")
        # limit=200 超过上限 100, 应被截断到 100 但不影响实际 3 条结果
        result = unified_search("FastAPI", limit=200)
        assert len(result["items"]) == 3

    def test_limit_zero_or_negative_clamped_to_one(self, temp_db):
        _insert_hotspot("h1", "FastAPI 热点", "")
        result = unified_search("FastAPI", limit=0)
        assert len(result["items"]) == 1

    def test_default_limit(self, temp_db):
        for i in range(25):
            _insert_hotspot(f"h{i}", f"FastAPI 第{i}篇", "")
        result = unified_search("FastAPI")
        assert len(result["items"]) == 20  # 默认 limit=20


class TestEmptyQuery:
    def test_empty_string_returns_empty(self, temp_db):
        _insert_hotspot("h1", "FastAPI", "")
        result = unified_search("")
        assert result["items"] == []
        assert result["grouped"] == {}

    def test_whitespace_only_returns_empty(self, temp_db):
        _insert_hotspot("h1", "FastAPI", "")
        result = unified_search("   ")
        assert result["items"] == []

    def test_none_query_returns_empty(self, temp_db):
        _insert_hotspot("h1", "FastAPI", "")
        result = unified_search(None)
        assert result["items"] == []


class TestLikeWildcardEscape:
    """用户输入 % 或 _ 不应被当作 LIKE 通配符。"""

    def test_percent_literal(self, temp_db):
        _insert_hotspot("h1", "100% 完成", "")
        _insert_hotspot("h2", "100X 完成", "")
        result = unified_search("100%")
        ids = [i["entity_id"] for i in result["items"]]
        assert "h1" in ids
        assert "h2" not in ids  # % 不应匹配 X

    def test_underscore_literal(self, temp_db):
        _insert_hotspot("h1", "a_b", "")
        _insert_hotspot("h2", "aXb", "")
        result = unified_search("a_b")
        ids = [i["entity_id"] for i in result["items"]]
        assert "h1" in ids
        assert "h2" not in ids  # _ 不应匹配 X


class TestGrouped:
    def test_grouped_by_entity_type(self, temp_db):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_hotspot("h2", "FastAPI 热点2", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        result = unified_search("FastAPI")
        assert len(result["grouped"]["hotspot"]) == 2
        assert len(result["grouped"]["knowledge"]) == 1

    def test_grouped_only_has_matching_types(self, temp_db):
        _insert_hotspot("h1", "FastAPI 热点", "")
        result = unified_search("FastAPI")
        assert "hotspot" in result["grouped"]
        assert "knowledge" not in result["grouped"]


class TestOrdering:
    def test_ordered_by_ingested_at_desc(self, temp_db):
        # h1 更早, h2 更晚 — 期望 h2 排在前面
        _insert_hotspot("h1", "FastAPI 旧", "", ingested_at="2026-01-01T00:00:00+00:00")
        _insert_hotspot("h2", "FastAPI 新", "", ingested_at="2026-07-01T00:00:00+00:00")
        result = unified_search("FastAPI")
        assert result["items"][0]["entity_id"] == "h2"
        assert result["items"][1]["entity_id"] == "h1"


class TestConvenienceMethods:
    def test_search_hotspots_only(self, temp_db):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        items = search_hotspots_only("FastAPI")
        assert len(items) == 1
        assert items[0]["entity_type"] == "hotspot"

    def test_search_knowledge_only(self, temp_db):
        _insert_hotspot("h1", "FastAPI 热点", "")
        _insert_knowledge("k1", "FastAPI 知识", "")
        items = search_knowledge_only("FastAPI")
        assert len(items) == 1
        assert items[0]["entity_type"] == "knowledge"


class TestPerformance:
    """验收 2: P95 < 500ms on 10k items (测试用 1k 代理验证)."""

    def test_p95_under_500ms(self, temp_db):
        from backend.repository.db import get_connection
        conn = get_connection()
        # 批量插入 1000 条热点
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (f"h{i}", f"FastAPI 第{i}篇标题", f"摘要{i}", "test",
             f"https://example.com/h{i}", "security", now, 50.0, now, 0,
             80, "[]", "pending", now)
            for i in range(1000)
        ]
        conn.executemany(
            """INSERT OR REPLACE INTO hotspots
               (id, title, summary, source, url, category, published_at, score,
                fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        # 跑 20 次取 P95
        timings = []
        for _ in range(20):
            t0 = time.perf_counter()
            unified_search("FastAPI", limit=20)
            timings.append((time.perf_counter() - t0) * 1000)
        timings.sort()
        p95 = timings[int(len(timings) * 0.95)]
        assert p95 < 500, f"P95={p95:.1f}ms exceeds 500ms budget"

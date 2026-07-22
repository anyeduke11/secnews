"""ExtractService 单元测试 — 三层提取器.

覆盖:
- 正则提取 (CVE/CNVD)
- 关键词提取 (LangChain/FastAPI/prompt injection)
- 分类→域映射
- 去重取最高置信度
- extract_and_attach (需 DB)
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db
from backend.services.extract_service import (
    extract_tags,
    extract_and_attach,
    _reload_rules,
)


@pytest.fixture(autouse=True)
def _reload_rules_each_test():
    """每个测试前重载规则缓存, 避免跨测试污染."""
    _reload_rules()
    yield
    _reload_rules()


class TestRegexExtract:
    def test_extract_cve(self):
        result = extract_tags("CVE-2026-1234 affects LangChain prompt injection.")
        tags = {r["tag_id"]: r["confidence"] for r in result}
        assert "cve" in tags
        assert tags["cve"] == 1.0

    def test_extract_cnvd(self):
        result = extract_tags("CNVD-2026-05678 漏洞预警")
        tags = {r["tag_id"] for r in result}
        assert "cnvd" in tags

    def test_extract_cnnvd(self):
        result = extract_tags("CNNVD-202601 漏洞通报")
        tags = {r["tag_id"] for r in result}
        assert "cnvd" in tags


class TestKeywordExtract:
    def test_extract_langchain(self):
        result = extract_tags("使用 LangChain 构建应用")
        tags = {r["tag_id"]: r["confidence"] for r in result}
        assert "langchain" in tags
        assert tags["langchain"] == 0.8

    def test_extract_fastapi(self):
        result = extract_tags("FastAPI 后端开发")
        tags = {r["tag_id"] for r in result}
        assert "fastapi" in tags

    def test_extract_prompt_injection(self):
        result = extract_tags("prompt injection 攻击防范")
        tags = {r["tag_id"] for r in result}
        assert "prompt-injection" in tags


class TestCategoryDomainExtract:
    def test_ai_category_adds_domain_tags(self):
        result = extract_tags("some text", category="ai")
        tags = {r["tag_id"] for r in result}
        assert "ai-security" in tags
        assert "llm" in tags

    def test_security_category_adds_domain_tags(self):
        result = extract_tags("some text", category="security")
        tags = {r["tag_id"] for r in result}
        assert "cve" in tags
        assert "vulnerability" in tags
        assert "network-security" in tags

    def test_finance_category(self):
        result = extract_tags("财报", category="finance")
        tags = {r["tag_id"] for r in result}
        assert "finance" in tags


class TestDedupAndMerge:
    def test_dedup_takes_highest_confidence(self):
        """cve 既被正则命中 (1.0) 又被分类映射 (0.5), 取 1.0."""
        result = extract_tags("CVE-2026-1234 漏洞", category="security")
        cve = [r for r in result if r["tag_id"] == "cve"]
        assert len(cve) == 1
        assert cve[0]["confidence"] == 1.0

    def test_sorted_by_confidence_desc(self):
        result = extract_tags("CVE-2026-1234 LangChain", category="ai")
        # cve (1.0) 应排在 langchain (0.8) 前面
        confidences = [r["confidence"] for r in result]
        assert confidences == sorted(confidences, reverse=True)

    def test_empty_text_returns_empty(self):
        assert extract_tags("") == []
        assert extract_tags("", "") == []


class TestExtractAndAttach:
    """extract_and_attach 需要 DB (TagRepository)."""

    @pytest.fixture
    def temp_db(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        test_db = tmp_path / "test_extract.db"
        monkeypatch.setattr(config, "db_path", test_db)
        db.close_db()
        db.init_db()
        yield test_db
        db.close_db()

    def test_attach_only_existing_tags(self, temp_db):
        """仅关联 tags 表中已存在的标签."""
        # 先创建热点 (FK 约束)
        from datetime import datetime, timedelta, timezone

        from backend.domain.enums import Category
        from backend.domain.models import HotspotItem
        from backend.repository.hotspot_repo import HotspotRepository

        now = datetime.now(timezone.utc)
        HotspotRepository().upsert_many([
            HotspotItem(
                id="h-test-1",
                title="Test",
                source="test",
                url="https://example.com/h-test-1",
                category=Category.SECURITY,
                published_at=now - timedelta(hours=1),
                fetched_at=now,
                ingested_at=now,
                summary="CVE-2026-1234 LangChain 漏洞",
            )
        ])
        # 种子标签 cve 已存在 (035 迁移), langchain 也存在
        attached = extract_and_attach(
            "h-test-1",
            text="CVE-2026-1234 LangChain 漏洞",
            category="security",
            min_confidence=0.5,
        )
        tag_ids = {t["tag_id"] for t in attached}
        assert "cve" in tag_ids
        assert "langchain" in tag_ids

        from backend.repository.tags_repo import TagRepository

        tags = TagRepository().list_by_hotspot("h-test-1")
        attached_ids = {t.id for t in tags}
        assert "cve" in attached_ids
        assert "langchain" in attached_ids

    def test_min_confidence_filter(self, temp_db):
        """低于 min_confidence 的标签不关联."""
        # 分类映射 confidence=0.5, 设 min=0.6 则不关联域标签
        attached = extract_and_attach(
            "h-test-2",
            text="普通文本无关键词",
            category="ai",
            min_confidence=0.6,
        )
        # ai-security 和 llm 都是 0.5, 应被过滤
        assert attached == []

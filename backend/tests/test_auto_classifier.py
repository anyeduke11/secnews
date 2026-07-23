"""Auto-classifier tests — domain/type/difficulty classification logic.

Tests the rule-based classifier without needing a DB connection.
"""

from __future__ import annotations

import pytest

from backend.services.auto_classifier import (
    classify_domain,
    classify_type,
    classify_difficulty,
    classify_item,
    batch_classify,
)


class TestClassifyDomain:
    """Domain classification from tags, title, and URL."""

    def test_from_tag_ai(self):
        assert classify_domain(["Agent", "模型", "效率工具"]) == "ai"

    def test_from_tag_security(self):
        assert classify_domain(["安全技术", "漏洞管理", "合规"]) == "security"

    def test_from_tag_finance(self):
        assert classify_domain(["金融科技", "银行业"]) == "finance"

    def test_from_tag_startup(self):
        assert classify_domain(["效率工具", "团队管理", "知识管理"]) == "startup"

    def test_from_tag_dev(self):
        assert classify_domain(["编程", "开源"]) == "dev"

    def test_from_title_ai(self):
        assert classify_domain([], "大模型训练指南") == "ai"

    def test_from_title_security(self):
        assert classify_domain([], "渗透测试入门指南") == "security"

    def test_from_title_finance(self):
        assert classify_domain([], "银行数字化转型方案") == "finance"

    def test_from_url(self):
        assert classify_domain([], "", "https://www.secrss.com/article") == "security"

    def test_no_match(self):
        assert classify_domain([], "无匹配关键词", "https://example.com") is None

    def test_tag_precedence_over_title(self):
        """Tags take priority over title."""
        assert classify_domain(["金融科技"], "AI Agent入门") == "finance"

    def test_title_fallback_when_no_tags(self):
        assert classify_domain([], "Claude使用技巧") == "ai"

    def test_tag_all_mixed(self):
        """First matching tag wins."""
        assert classify_domain(["安全技术", "Agent"]) == "security"


class TestClassifyType:
    def test_from_tag_tutorial(self):
        assert classify_type(["教程实操"]) == "tutorial"

    def test_from_tag_tool(self):
        assert classify_type(["效率工具"]) == "tool"

    def test_from_tag_news(self):
        assert classify_type(["资讯"]) == "news"

    def test_from_tag_standard(self):
        assert classify_type(["标准规范"]) == "standard"

    def test_from_tag_paper(self):
        assert classify_type(["技术原理"]) == "paper"

    def test_no_match(self):
        assert classify_type(["通用标签"]) is None

    def test_from_title_tutorial(self):
        assert classify_type([], "从零开始的教程") == "tutorial"

    def test_from_title_standard(self):
        assert classify_type([], "新规出台：数据安全管理办法") == "standard"


class TestClassifyDifficulty:
    def test_from_tag_beginner(self):
        assert classify_difficulty(["教程实操"]) == "beginner"

    def test_from_tag_advanced(self):
        assert classify_difficulty(["技术原理"]) == "advanced"

    def test_no_match(self):
        assert classify_difficulty(["通用标签"]) is None

    def test_from_title_beginner(self):
        assert classify_difficulty([], "入门指南") == "beginner"

    def test_from_title_advanced(self):
        assert classify_difficulty([], "深入理解内核原理") == "advanced"


class TestClassifyItem:
    def test_full_classification(self):
        result = classify_item(["Agent", "教程实操"], "AI Agent入门", "https://example.com")
        assert result["domain"] == "ai"
        assert result["type"] == "tutorial"
        assert result["difficulty"] == "beginner"

    def test_no_tags_no_title(self):
        result = classify_item([], "", "")
        assert result["domain"] is None
        assert result["type"] is None
        assert result["difficulty"] is None

    def test_no_tags_with_good_title(self):
        result = classify_item([], "渗透测试实战：从入门到进阶")
        assert result["domain"] == "security"


class TestBatchClassify:
    def test_batch_updates_in_place(self):
        items = [
            {"id": "1", "title": "AI Agent教程", "tags": ["Agent", "教程实操"], "source_url": "https://example.com"},
            {"id": "2", "title": "安全事件分析", "tags": ["安全事件"], "source_url": "https://secrss.com"},
            {"id": "3", "title": "无标题", "tags": [], "source_url": ""},
        ]
        results = batch_classify(items)
        assert len(results) == 3
        assert results[0]["domain"] == "ai"
        assert results[1]["domain"] == "security"
        assert results[2]["domain"] is None

    def test_batch_string_tags(self):
        items = [
            {"id": "1", "title": "Test", "tags": '["安全技术"]', "source_url": ""},
        ]
        results = batch_classify(items)
        assert results[0]["domain"] == "security"

    def test_batch_string_tags_empty(self):
        items = [
            {"id": "1", "title": "Test", "tags": "invalid json", "source_url": ""},
        ]
        results = batch_classify(items)
        assert results[0]["domain"] is None  # falls through to no match
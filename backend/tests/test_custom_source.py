"""Phase 8 Addendum 8.4: custom_sources CRUD + 关键词分类

测试范围
--------
- :func:`backend.api.sources.classify_by_url_and_title` 五种典型场景
- 用例聚焦分类逻辑（纯函数），不触网
"""
from __future__ import annotations

import pytest

from backend.api.sources import classify_by_url_and_title


def test_classify_by_url_and_title_ai():
    assert classify_by_url_and_title("https://openai.com/blog", "OpenAI Blog") == "ai"


def test_classify_by_url_and_title_security():
    assert classify_by_url_and_title(
        "https://krebsonsecurity.com", "Krebs on Security"
    ) == "security"


def test_classify_by_url_and_title_github():
    assert classify_by_url_and_title(
        "https://github.com/trending", "GitHub Trending"
    ) == "github"


def test_classify_by_url_and_title_default_ai():
    """无任何已知关键词 → fallback 到 'ai'。"""
    assert classify_by_url_and_title("https://unknown.com", "Random Stuff") == "ai"


def test_classify_by_url_and_title_finance_chinese():
    assert classify_by_url_and_title("https://finance.sina.com.cn", "新浪财经") == "finance"


def test_classify_by_url_and_title_bid():
    """政府采购/招标关键词命中 bid。"""
    assert classify_by_url_and_title(
        "https://www.tender.gov.cn", "中国政府采购网"
    ) == "bid"

"""Phase 8 Addendum 8.4: custom_sources CRUD + 关键词分类 + SSRF 防护

测试范围
--------
- :func:`backend.api.sources.classify_by_url_and_title` 五种典型场景
- v0.7.x P0: ``_probe_url`` SSRF 防御 (localhost / 私网 IP 拒收)
- 用例聚焦分类逻辑（纯函数）+ 防御性测试，不触网
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


# ---------------------------------------------------------------------------
# v0.7.x P0: SSRF 防护 — _probe_url 应拒收 localhost / 私网 / 保留 IP
# ---------------------------------------------------------------------------
class TestProbeUrlSSRFDefense:
    """``_probe_url`` 拒绝命中 SSRF 黑名单的 URL, 返回 ok=False + ssrf_block error。

    Defense in depth: 即使 ``add_custom_source`` 已先验过, ``_probe_url`` 仍做兜底
    (防 DB 内 url 被改 / 重 probe 时 url 已变更 / 直接调 ``_probe_url`` 的内部路径)。
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_url",
        [
            "http://localhost/feed.xml",
            "http://127.0.0.1:8080/",
            "http://10.0.0.1/",
            "http://192.168.1.100/",
            "http://169.254.169.254/latest/meta-data/",  # AWS metadata
            "http://[::1]/",
        ],
    )
    async def test_ssrf_blocked(self, bad_url):
        """私网 / loopback IP / 域名应被拒收 (ok=False, error 含 ssrf_block)。"""
        from backend.api.sources import _probe_url
        result = await _probe_url(bad_url)
        assert result["ok"] is False
        assert "ssrf_block" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_public_url_passes_ssrf_check(self):
        """公网域名应通过 SSRF 校验 (实际 probe 仍可能 HTTP 失败, 但不应是 ssrf_block)。"""
        from backend.api.sources import _probe_url
        # example.com 解析到公网 IP, 应通过 SSRF check
        # 即使实际 HTTP 失败 (mock 无), 错误也不应是 ssrf_block
        result = await _probe_url("https://example.com/feed")
        # ok=False 可能因为连接失败, 但 error 不含 "ssrf_block"
        if not result["ok"]:
            assert "ssrf_block" not in result.get("error", ""), (
                f"公网域名不应触发 ssrf_block, got: {result}"
            )

"""Pure-function tests for simhash, Hamming distance, URL/title normalization.

Covers
------
- Collision: same input → same fingerprint
- Hamming distance: similar texts close, different texts far
- URL canonicalization: tracking params, protocol, hash, trailing slash
- Empty / whitespace edge cases
- Long text and special characters
"""

from __future__ import annotations

import pytest

from backend.services.simhash import (
    canonicalize_url,
    hamming_distance,
    normalize_title,
    simhash,
)


# ---------------------------------------------------------------------------
# Collision test
# ---------------------------------------------------------------------------

class TestCollision:
    """Same input must produce the same simhash value."""

    def test_identical_inputs(self):
        a = simhash("中国成功发射新型卫星 6G通信技术取得突破")
        b = simhash("中国成功发射新型卫星 6G通信技术取得突破")
        assert a == b

    def test_different_inputs_differ(self):
        a = simhash("OpenAI发布GPT-5模型 推理能力大幅提升")
        b = simhash("今日A股三大指数集体收涨 成交额突破万亿")
        assert a != b

    def test_deterministic_multiple_calls(self):
        text = "The quick brown fox jumps over the lazy dog"
        results = [simhash(text) for _ in range(5)]
        assert all(r == results[0] for r in results)


# ---------------------------------------------------------------------------
# Hamming distance test
# ---------------------------------------------------------------------------

class TestHammingDistance:
    """Similar texts should have small Hamming distance; different texts large."""

    def test_similar_texts_close(self):
        """Near-duplicate texts should have lower Hamming distance than unrelated texts."""
        # Strictly identical
        t1 = "Apple announces new MacBook Pro with M4 chip"
        assert hamming_distance(simhash(t1), simhash(t1)) == 0

        # Very similar — extra word
        t2 = "Apple announces new MacBook Pro with M4 chip performance"
        similar_d = hamming_distance(simhash(t1), simhash(t2))
        assert similar_d < 8, f"Expected < 8 for similar texts, got {similar_d}"

        # Unrelated — should be much farther
        t3 = "今日A股三大指数集体收涨 成交额突破万亿"
        far_d = hamming_distance(simhash(t1), simhash(t3))
        assert far_d > 10, f"Expected > 10 for unrelated texts, got {far_d}"
        # Far should be farther than similar
        assert far_d > similar_d, f"Unrelated text ({far_d}) should be farther than similar ({similar_d})"

    def test_different_texts_far(self):
        """Completely different texts should have Hamming distance > 10."""
        t1 = "中国成功发射新型卫星 6G通信技术取得突破"
        t2 = "OpenAI发布GPT-5模型 推理能力大幅提升 引发行业关注"
        d = hamming_distance(simhash(t1), simhash(t2))
        assert d > 10, f"Expected > 10, got {d}"

    def test_zero_distance_for_identical(self):
        a = simhash("identical text")
        assert hamming_distance(a, a) == 0


# ---------------------------------------------------------------------------
# URL canonicalization test
# ---------------------------------------------------------------------------

class TestCanonicalizeUrl:
    """URL normalization — tracking params, protocol, hash, trailing slash."""

    def test_remove_tracking_params(self):
        url = "https://example.com/page?utm_source=twitter&utm_medium=social&id=123"
        result = canonicalize_url(url)
        assert result == "https://example.com/page?id=123"

    def test_remove_fbclid(self):
        url = "https://example.com/article?fbclid=abc123&page=2"
        result = canonicalize_url(url)
        assert result == "https://example.com/article?page=2"

    def test_remove_gclid(self):
        url = "https://example.com/product?gclid=xyz789&ref=nav"
        result = canonicalize_url(url)
        assert result == "https://example.com/product?ref=nav"

    def test_unify_protocol(self):
        url = "http://example.com/path"
        result = canonicalize_url(url)
        assert result == "https://example.com/path"

    def test_remove_fragment(self):
        url = "https://example.com/page#section"
        result = canonicalize_url(url)
        assert "#" not in result
        assert result == "https://example.com/page"

    def test_lowercase_domain(self):
        url = "https://Example.COM/Path"
        result = canonicalize_url(url)
        assert result == "https://example.com/Path"

    def test_remove_trailing_slash(self):
        url = "https://example.com/page/"
        result = canonicalize_url(url)
        assert result == "https://example.com/page"

    def test_multiple_tracking_params(self):
        url = ("https://example.com/article?"
               "utm_source=twitter&utm_medium=social&"
               "utm_campaign=launch&fbclid=abc&"
               "gclid=xyz&mc_cid=123&mc_eid=456&"
               "real_param=keep")
        result = canonicalize_url(url)
        assert result == "https://example.com/article?real_param=keep"


# ---------------------------------------------------------------------------
# Empty / whitespace input test
# ---------------------------------------------------------------------------

class TestEmptyInput:
    """Empty and whitespace-only inputs must be handled gracefully."""

    def test_simhash_empty(self):
        assert simhash("") == 0

    def test_simhash_whitespace(self):
        assert simhash("   ") == 0
        assert simhash("\t\n") == 0

    def test_canonicalize_url_empty(self):
        assert canonicalize_url("") == ""
        assert canonicalize_url("  ") == ""

    def test_normalize_title_empty(self):
        assert normalize_title("") == ""
        assert normalize_title("   ") == ""


# ---------------------------------------------------------------------------
# Boundary and special characters test
# ---------------------------------------------------------------------------

class TestBoundary:
    """Long text, special characters, mixed content."""

    def test_very_long_text(self):
        """Simhash of a very long text must still produce a valid 64-bit int."""
        long_text = "安全 " * 1000
        result = simhash(long_text)
        assert isinstance(result, int)
        assert 0 <= result <= 0xFFFFFFFFFFFFFFFF
        # Deterministic
        assert simhash(long_text) == result

    def test_special_characters(self):
        """Special characters should not cause errors."""
        text = "!@#$%^&*()_+-=[]{}|;':\",./<>?`~"
        result = simhash(text)
        assert isinstance(result, int)
        assert 0 <= result <= 0xFFFFFFFFFFFFFFFF

    def test_mixed_cjk_ascii(self):
        """Mixed CJK and ASCII content."""
        text = "【重磅】OpenAI GPT-5 发布！🚀 性能提升100%？"
        result = simhash(text)
        assert isinstance(result, int)
        assert 0 <= result <= 0xFFFFFFFFFFFFFFFF

    def test_normalize_title_special_chars(self):
        """normalize_title strips punctuation but keeps CJK and alphanumeric."""
        title = "【重磅】OpenAI GPT-5 发布！🚀 性能提升100%？"
        result = normalize_title(title)
        # Emoji and punctuation removed, CJK/alpha/numbers kept
        assert "重磅" in result
        assert "openai" in result
        assert "gpt" in result
        assert "100" in result
        assert "!" not in result
        assert "【" not in result
        assert "🚀" not in result

    def test_normalize_title_collapse_whitespace(self):
        title = "hello    world   test"
        result = normalize_title(title)
        assert result == "hello world test"

    def test_simhash_64bit_range(self):
        """Ensure simhash output is always within 64-bit unsigned range."""
        texts = [
            "short",
            "a" * 100,
            "你好世界",
            "Mixed CN 中文 English 123 !@#",
        ]
        for t in texts:
            h = simhash(t)
            assert 0 <= h <= 0xFFFFFFFFFFFFFFFF, f"Out of range for: {t!r}"
"""可读 ID 工厂测试 — 验证 ID 格式、唯一性和特殊字符处理。"""

from __future__ import annotations

import pytest

from backend.collectors.id_factory import make_readable_id


class TestMakeReadableId:
    """make_readable_id 基本格式验证。"""

    def test_make_readable_id(self) -> None:
        """验证 format: {source}:{subtype}:{native_id}"""
        assert make_readable_id("hn", "item", "12345678") == "hn:item:12345678"
        assert make_readable_id("reddit", "post", "abc123") == "reddit:post:abc123"
        assert make_readable_id("github", "issue", "42") == "github:issue:42"

    def test_readable_id_uniqueness(self) -> None:
        """相同 source+subtype+native_id 产生相同结果。"""
        r1 = make_readable_id("hn", "item", "12345678")
        r2 = make_readable_id("hn", "item", "12345678")
        assert r1 == r2

        # 不同的 native_id 产生不同的结果
        r3 = make_readable_id("hn", "item", "87654321")
        assert r1 != r3

        # 不同的 source 产生不同的结果
        r4 = make_readable_id("reddit", "item", "12345678")
        assert r1 != r4

    def test_readable_id_special_chars(self) -> None:
        """native_id 中的特殊字符被正确处理。"""
        # 空格 → 连字符
        assert make_readable_id("hn", "item", "story 123") == "hn:item:story-123"

        # 大小写归一化
        assert make_readable_id("HN", "Item", "ABC123") == "hn:item:abc123"

        # 特殊字符被剥离
        assert make_readable_id("hn", "item", "abc!@#123") == "hn:item:abc123"

        # 混合场景
        assert make_readable_id("Reddit", "Post", "t3_abc def") == "reddit:post:t3_abc-def"

    def test_empty_values_raise_error(self) -> None:
        """空值或 None 抛出 ValueError。"""
        with pytest.raises(ValueError):
            make_readable_id("", "item", "123")
        with pytest.raises(ValueError):
            make_readable_id("hn", "", "123")
        with pytest.raises(ValueError):
            make_readable_id("hn", "item", "")
        with pytest.raises(ValueError):
            make_readable_id(None, "item", "123")  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            make_readable_id("hn", None, "123")  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            make_readable_id("hn", "item", None)  # type: ignore[arg-type]

    def test_whitespace_normalized(self) -> None:
        """各种空白字符被归一化为连字符。"""
        assert make_readable_id("hn", "item", "a  b") == "hn:item:a-b"
        assert make_readable_id("hn", "item", "a\tb") == "hn:item:a-b"
        assert make_readable_id("hn", "item", "a\nb") == "hn:item:a-b"
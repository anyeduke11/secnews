"""trafilatura parser tests — 3 用例覆盖正常提取 / 失败回退 / 未安装。

由于 trafilatura 是可选依赖，所有测试均通过 mock 模拟 trafilatura 行为。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.parsers.trafilatura_parser import extract_content


class TestTrafilaturaExtract:
    """trafilatura 提取器测试套件。"""

    def test_trafilatura_extract(self) -> None:
        """Mock trafilatura 返回提取结果，验证返回 dict 含所有预期键。"""
        mock_result = {
            "title": "Test Title",
            "text": "Test content body.",
            "author": "Test Author",
            "date": "2026-07-31",
            "categories": ["tech", "security"],
            "tags": ["python", "testing"],
        }

        mock_trafilatura = MagicMock()
        mock_trafilatura.extract.return_value = mock_result

        with patch("backend.parsers.trafilatura_parser.HAS_TRAFILATURA", True):
            with patch("backend.parsers.trafilatura_parser.trafilatura", mock_trafilatura):
                result = extract_content("<html><body>test</body></html>", "https://example.com")

        assert result is not None
        assert result["title"] == "Test Title"
        assert result["text"] == "Test content body."
        assert result["author"] == "Test Author"
        assert result["date"] == "2026-07-31"
        assert result["categories"] == ["tech", "security"]
        assert result["tags"] == ["python", "testing"]

    def test_trafilatura_fallback(self) -> None:
        """Mock trafilatura 提取失败（返回 None），验证返回 None。"""
        mock_trafilatura = MagicMock()
        mock_trafilatura.extract.return_value = None

        with patch("backend.parsers.trafilatura_parser.HAS_TRAFILATURA", True):
            with patch("backend.parsers.trafilatura_parser.trafilatura", mock_trafilatura):
                result = extract_content("<html><body>test</body></html>", "https://example.com")

        assert result is None

    def test_trafilatura_not_installed(self) -> None:
        """模拟 trafilatura 未安装，验证 HAS_TRAFILATURA=False 且 extract 返回 None。"""
        with patch("backend.parsers.trafilatura_parser.HAS_TRAFILATURA", False):
            result = extract_content("<html><body>test</body></html>", "https://example.com")

        assert result is None
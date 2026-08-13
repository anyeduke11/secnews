"""trafilatura HTML 内容提取器（可选依赖）。

当 trafilatura 未安装时，extract_content() 返回 None 且不报错。
调用方应检查 HAS_TRAFILATURA 标志或直接处理 None 返回值。

用法::

    from backend.parsers.trafilatura_parser import extract_content, HAS_TRAFILATURA

    if HAS_TRAFILATURA:
        result = extract_content(html, url)
        if result:
            print(result["title"], result["text"])
"""
from __future__ import annotations

from loguru import logger

try:
    import trafilatura

    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False
    trafilatura = None  # type: ignore[assignment]
    logger.warning("trafilatura not installed; HTML extraction disabled")


def extract_content(html: str, url: str) -> dict | None:
    """使用 trafilatura 从 HTML 提取结构化内容。

    Args:
        html: 原始 HTML 字符串。
        url: 来源 URL（trafilatura 内部用于相对 URL 解析）。

    Returns:
        dict 包含以下键：title / text / author / date / categories / tags。
        提取失败或 trafilatura 未安装时返回 None。
    """
    if not HAS_TRAFILATURA:
        return None

    try:
        result = trafilatura.extract(
            html,
            url=url,
            output_format="python",
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
    except Exception:
        logger.warning("trafilatura extraction failed for {}", url)
        return None

    if result is None or not isinstance(result, dict):
        return None

    return {
        "title": result.get("title", ""),
        "text": result.get("text", ""),
        "author": result.get("author", ""),
        "date": result.get("date", ""),
        "categories": result.get("categories", []),
        "tags": result.get("tags", []),
    }


__all__ = ["HAS_TRAFILATURA", "extract_content"]
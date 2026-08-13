"""URL 规范化工具 — 用于三层去重第 1 层。

规则：
1. 移除尾部斜杠（保留根路径 /）
2. 小写 host
3. 移除 fragment
4. 移除 www. 前缀
"""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def canonicalize_url(url: str) -> str:
    """规范化 URL，返回可比较的规范形式。

    >>> canonicalize_url("https://www.example.com/path/")
    'https://example.com/path'
    >>> canonicalize_url("HTTP://Example.COM/Path#frag")
    'http://example.com/Path'
    >>> canonicalize_url("https://example.com/")
    'https://example.com/'
    """
    if not url:
        return url

    parsed = urlparse(url)
    # 小写 host，移除 www. 前缀
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    host = host.lower()

    # 保留 scheme 和 path
    scheme = parsed.scheme.lower()
    path = parsed.path or "/"

    # 移除尾部斜杠（保留根路径 /）
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # 重建 URL（丢弃 fragment, query, params）
    # 注意：保留 query 可能会影响去重准确性，这里丢弃 query
    # 因为 query 参数通常用于跟踪而非内容标识
    canonical = urlunparse((scheme, host, path, "", "", ""))
    return canonical


def urls_are_duplicate(url_a: str, url_b: str) -> bool:
    """判断两个 URL 是否重复（规范化后比较）。

    Args:
        url_a: 第一个 URL
        url_b: 第二个 URL

    Returns:
        规范化后相同返回 True
    """
    return canonicalize_url(url_a) == canonicalize_url(url_b)


__all__ = ["canonicalize_url", "urls_are_duplicate"]
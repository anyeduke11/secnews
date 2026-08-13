"""OpenBB 金融数据平台热点采集器 (Phase 11)。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.FINANCE``
- ``sources``   : OpenBB blog 页面
- 走默认 aiohttp 抓取路径 (``_fetch_source`` → ``_parse_html``)
- Phase 13 硬约束: 源全部失败时直接返回空列表

V1.9 变更: RSS 路径 (https://openbb.co/rss/) 已失效 (404), 改为
直接抓取 blog 首页 (https://openbb.co/blog) 走 aiohttp HTML 解析。
"""
from __future__ import annotations

from backend.collectors.base import BaseCollector
from backend.domain.enums import Category

OPENBB_SOURCES: list[dict] = [
    {
        "name": "OpenBB",
        "url": "https://openbb.co/blog",
        "score": 78,
        "keywords": ["finance", "data", "analysis"],
    },
]


class OpenBBCollector(BaseCollector):
    """采集 OpenBB 金融数据平台热点资讯。

    V1.9: RSS 路径已失效, 走默认 aiohttp HTML 抓取 + _parse_html 解析。
    """

    category = Category.FINANCE
    sources = OPENBB_SOURCES


__all__ = ["OpenBBCollector", "OPENBB_SOURCES"]
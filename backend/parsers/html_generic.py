"""通用 HTML 解析器 — 仅允许配置化 CSS 选择器。

Phase 1.2 (Crawler v2): 作为非 P0 源的兜底解析器。
使用通用正则提取 <a href> 链接。

用法:
    parser = HtmlGenericParser()
    items = parser.parse(html, url)
"""
from __future__ import annotations

import re

from backend.parsers.base_parser import BaseSourceParser, RawItem

SOURCE_ID = "html_generic"
VERSION = "1.0.0"

# 通用 <a href> 提取
_A_HREF_RE = re.compile(
    r'<a[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>[^<]{8,})</a>',
    re.IGNORECASE,
)


class HtmlGenericParser(BaseSourceParser):
    """通用 HTML 解析器。"""

    source_id = SOURCE_ID
    version = VERSION

    def _do_parse(self, content: str, url: str, content_type: str = "html") -> list[RawItem]:
        items: list[RawItem] = []
        seen: set[str] = set()

        for m in _A_HREF_RE.finditer(content):
            raw_url = m.group("url").strip()
            title = m.group("title").strip()
            if not raw_url or not title:
                continue
            title = title.replace("&nbsp;", " ").replace("&amp;", "&")
            if raw_url.startswith("http"):
                href = raw_url
            elif raw_url.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                href = f"{parsed.scheme}://{parsed.netloc}{raw_url}"
            else:
                href = url.rstrip("/") + "/" + raw_url.lstrip("/")
            if href in seen:
                continue
            seen.add(href)
            items.append(RawItem(title=title, url=href))
            if len(items) >= 50:
                break

        return items


__all__ = ["HtmlGenericParser", "SOURCE_ID", "VERSION"]
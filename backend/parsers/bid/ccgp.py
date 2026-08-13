"""中国政府采购网 (ccgp.gov.cn) 解析器。

站点结构:
- 列表页: https://www.ccgp.gov.cn/cggg/zygg/
- 条目: <li><a href="..." title="...">标题</a> <span>日期</span></li>
- 详情页: 标准文章页

Phase 1.2 (Crawler v2): 独立解析器，可单独测试。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from backend.parsers.base_parser import BaseSourceParser, RawItem

SOURCE_ID = "bid_ccgp"
VERSION = "1.0.0"

# 条目正则: <li><a href="..." title="...">标题</a> <span>日期</span></li>
_ITEM_RE = re.compile(
    r'<li[^>]*>.*?<a[^>]+href="(?P<url>[^"]+)"[^>]*title="(?P<title>[^"]*)"[^>]*>'
    r"(?:.*?</a>)?.*?<span[^>]*>(?P<date>\d{4}[-/]\d{1,2}[-/]\d{1,2})</span>.*?</li>",
    re.IGNORECASE | re.DOTALL,
)

# 兜底: 简单的 <a href> 提取
_FALLBACK_A_RE = re.compile(
    r'<a[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>[^<]{8,})</a>',
    re.IGNORECASE,
)


class CcgpParser(BaseSourceParser):
    """中国政府采购网解析器。"""

    source_id = SOURCE_ID
    version = VERSION

    def _do_parse(self, content: str, url: str, content_type: str = "html") -> list[RawItem]:
        items: list[RawItem] = []
        seen: set[str] = set()

        # 优先匹配 li 结构
        for m in _ITEM_RE.finditer(content):
            raw_url = m.group("url").strip()
            title = m.group("title").strip()
            date_str = m.group("date").strip()
            if not raw_url or not title:
                continue
            title = title.replace("&nbsp;", " ").replace("&amp;", "&")
            href = raw_url if raw_url.startswith("http") else f"https://www.ccgp.gov.cn{raw_url}"
            if href in seen:
                continue
            seen.add(href)
            published_at = _parse_date(date_str)
            items.append(RawItem(title=title, url=href, published_at=published_at))
            if len(items) >= 50:
                break

        # 兜底: 简单 <a href> 提取
        if not items:
            for m in _FALLBACK_A_RE.finditer(content):
                raw_url = m.group("url").strip()
                title = m.group("title").strip()
                if not raw_url or not title:
                    continue
                title = title.replace("&nbsp;", " ").replace("&amp;", "&")
                href = raw_url if raw_url.startswith("http") else f"https://www.ccgp.gov.cn{raw_url}"
                if href in seen:
                    continue
                seen.add(href)
                items.append(RawItem(title=title, url=href))
                if len(items) >= 50:
                    break

        return items


def _parse_date(date_str: str) -> str | None:
    """解析日期字符串为 ISO 格式。"""
    try:
        date_str = date_str.replace("/", "-")
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None


__all__ = ["CcgpParser", "SOURCE_ID", "VERSION"]
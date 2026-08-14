"""中国采购与招标网 (chinabidding.com.cn) 解析器。

站点结构:
- 列表页: https://www.chinabidding.com.cn/zbgg/
- 条目: <div class="list-item"><a href="...">标题</a><span>日期</span></div>
- 详情页: 标准文章页

Phase 1.2 (Crawler v2): 独立解析器，可单独测试。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from backend.parsers.base_parser import BaseSourceParser, RawItem

SOURCE_ID = "bid_chinabidding"
VERSION = "1.0.0"

# 条目正则: <div class="list-item"> ... <a href="...">标题</a> ... <span>日期</span> ... </div>
_ITEM_RE = re.compile(
    r'<div[^>]*class="[^"]*list-item[^"]*"[^>]*>.*?'
    r'<a[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>[^<]+)</a>.*?'
    r"(?P<date>\d{4}[-/]\d{1,2}[-/]\d{1,2}).*?</div>",
    re.IGNORECASE | re.DOTALL,
)

_FALLBACK_A_RE = re.compile(
    r'<a[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>[^<]{8,})</a>',
    re.IGNORECASE,
)


class ChinabiddingParser(BaseSourceParser):
    """中国采购与招标网解析器。"""

    source_id = SOURCE_ID
    version = VERSION

    def _do_parse(self, content: str, url: str, content_type: str = "html") -> list[RawItem]:
        items: list[RawItem] = []
        seen: set[str] = set()

        for m in _ITEM_RE.finditer(content):
            raw_url = m.group("url").strip()
            title = m.group("title").strip()
            date_str = m.group("date").strip()
            if not raw_url or not title:
                continue
            title = title.replace("&nbsp;", " ").replace("&amp;", "&")
            href = raw_url if raw_url.startswith("http") else f"https://www.chinabidding.com.cn{raw_url}"
            if href in seen:
                continue
            seen.add(href)
            published_at = _parse_date(date_str)
            items.append(RawItem(title=title, url=href, published_at=published_at))
            if len(items) >= 50:
                break

        if not items:
            for m in _FALLBACK_A_RE.finditer(content):
                raw_url = m.group("url").strip()
                title = m.group("title").strip()
                if not raw_url or not title:
                    continue
                title = title.replace("&nbsp;", " ").replace("&amp;", "&")
                href = raw_url if raw_url.startswith("http") else f"https://www.chinabidding.com.cn{raw_url}"
                if href in seen:
                    continue
                seen.add(href)
                items.append(RawItem(title=title, url=href))
                if len(items) >= 50:
                    break

        return items


def _parse_date(date_str: str) -> str | None:
    try:
        date_str = date_str.replace("/", "-")
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None


__all__ = ["SOURCE_ID", "VERSION", "ChinabiddingParser"]
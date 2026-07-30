"""财联社（CLSD）Telegraph 列表 — HTML 解析器。

源: https://www.cls.cn/telegraph
格式: ``<a class="subject-content" href="/detail/...">HH:MM:SS...</a>``
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from backend.parsers.base_parser import BaseSourceParser, RawItem

SOURCE_ID = "clsd"

_TELEGRAPH_TIME_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})")
_LINK_RE = re.compile(
    r'<a[^>]+class=["\']subject-content["\']'
    r'[^>]+href=["\']([^"\']+)["\']'
    r'[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


class ClsdParser(BaseSourceParser):
    source_id = SOURCE_ID
    version = "1.0.0"

    def _do_parse(self, content: str, url: str, content_type: str) -> list[RawItem]:
        items: list[RawItem] = []
        for m in _LINK_RE.finditer(content):
            href, body = m.group(1), m.group(2)
            text = re.sub(r"<[^>]+>", "", body).strip()
            if not text or len(text) < 8:
                continue
            # 提取电报前缀时间 "HH:MM:SS"
            t = _TELEGRAPH_TIME_RE.match(text)
            published_at = None
            if t:
                h, mi, s = int(t.group(1)), int(t.group(2)), int(t.group(3))
                now = datetime.now(timezone(timedelta(hours=8)))
                dt = now.replace(hour=h, minute=mi, second=s, microsecond=0)
                if dt > now:
                    dt = dt.replace(day=dt.day - 1)
                published_at = dt.astimezone(timezone.utc).isoformat()
            item_url = href if href.startswith("http") else f"https://www.cls.cn{href}"
            items.append(RawItem(
                title=text,
                url=item_url,
                published_at=published_at,
            ))
        return items


__all__ = ["ClsdParser", "SOURCE_ID"]
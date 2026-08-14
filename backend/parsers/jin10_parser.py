"""金十数据 7×24 快讯 — JS 变量 JSON 解析器。

源: https://www.jin10.com/
格式: ``var newest = [{...}, {...}]``
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from backend.parsers.base_parser import BaseSourceParser, RawItem

SOURCE_ID = "jin10"

_JIN10_PREFIX_RE = re.compile(r"var newest\s*=\s*", re.IGNORECASE)
_JIN10_SUFFIX_RE = re.compile(r";\s*$")


def _parse_jin10_time(time_str: str) -> str | None:
    """金十 data.time → ISO 8601 UTC."""
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))  # 北京时间
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


class Jin10Parser(BaseSourceParser):
    source_id = SOURCE_ID
    version = "1.0.0"

    def _do_parse(self, content: str, url: str, content_type: str) -> list[RawItem]:
        items: list[RawItem] = []
        raw = _JIN10_PREFIX_RE.sub("", content.strip())
        raw = _JIN10_SUFFIX_RE.sub("", raw)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return items
        if not isinstance(data, list):
            return items

        for entry in data:
            if not isinstance(entry, dict):
                continue
            # channel=5 是 VIP/付费内容，跳过
            if 5 in (entry.get("channel") or []):
                continue
            d = entry.get("data") or {}
            text = d.get("title") or d.get("content") or ""
            text = re.sub(r"</?b>", "", text).strip()
            if not text:
                continue
            # 拆【title】desc 格式
            m = re.match(r"^【([^】]*)】(.*)$", text)
            title = (m.group(1) or text).strip() if m else text
            if not title or len(title) < 8:
                continue
            item_url = f"https://flash.jin10.com/detail/{entry.get('id')}"
            published_at = _parse_jin10_time(entry.get("time") or "")
            items.append(RawItem(
                title=title,
                url=item_url,
                published_at=published_at,
            ))
        return items


__all__ = ["SOURCE_ID", "Jin10Parser"]
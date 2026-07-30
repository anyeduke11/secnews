"""AIhot 每日 AI 热点聚合 — JSON API 解析器。

源: https://aihot.virxact.com/
API: https://aihot.virxact.com/api/public/items?mode=all&take=30
"""
from __future__ import annotations

import json
from typing import Any

from backend.parsers.base_parser import BaseSourceParser, RawItem

SOURCE_ID = "aihot"


class AihotParser(BaseSourceParser):
    source_id = SOURCE_ID
    version = "1.0.0"

    def _do_parse(self, content: str, url: str, content_type: str) -> list[RawItem]:
        items: list[RawItem] = []
        try:
            data = json.loads(content) if isinstance(content, str) else content
        except (json.JSONDecodeError, TypeError):
            return items

        entries = (data or {}).get("items") or []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            title = (entry.get("title") or "").strip()
            entry_url = (entry.get("url") or "").strip()
            if not title or not entry_url:
                continue
            items.append(RawItem(
                title=title,
                url=entry_url,
                summary=(entry.get("summary") or "").strip(),
                published_at=entry.get("publishedAt"),
            ))
        return items


__all__ = ["AihotParser", "SOURCE_ID"]
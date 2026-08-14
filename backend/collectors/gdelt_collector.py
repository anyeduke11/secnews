"""GDELT 全球事件数据库采集器（Phase 11 延迟实现）。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.SECURITY``
- ``sources``   : GDELT API v2 (JSON API 路径)
- ``timeout``   : 30s（默认）

Phase 13 硬约束: 不生成 fallback 数据, 失败时直接返回空列表。
Phase 11 延迟实现: 如遇到反爬, collect() 返回空并记录 warning。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.collectors.base import BaseCollector
from backend.collectors.id_factory import make_readable_id
from backend.domain.enums import Category

GDELT_SOURCES: list[dict] = [
    {
        "name": "GDELT",
        "url": "https://api.gdeltproject.org/api/v2/",
        "api_url": "https://api.gdeltproject.org/api/v2/doc/doc?query=cyber+security&mode=artlist&format=json&max=25",
        "score": 76,
        "keywords": ["security", "global", "events"],
        "renderer": "json",
    },
]


class GDELTCollector(BaseCollector):
    """采集 GDELT 全球事件数据库中的安全相关新闻。"""

    category = Category.SECURITY
    sources = GDELT_SOURCES

    def _parse_json(
        self, data: Any, source: dict
    ) -> list[dict[str, Any]]:
        """GDELT JSON API 解析。

        GDELT v2 doc API 响应格式:
          {"articles": [
              {"url": "...", "title": "...",
               "seendate": "20260629T050000Z", "domain": "...", ...},
          ]}
        """
        articles = (data or {}).get("articles") or []
        out: list[dict[str, Any]] = []
        for i, entry in enumerate(articles):
            if not isinstance(entry, dict):
                continue
            title = (entry.get("title") or "").strip()
            url = (entry.get("url") or "").strip()
            if not title or not url:
                continue
            seendate = entry.get("seendate", "")
            published_at: datetime | None = None
            if seendate:
                try:
                    published_at = datetime.strptime(
                        seendate, "%Y%m%dT%H%M%SZ"
                    ).replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass
            readable_id = make_readable_id("gdelt", "article", str(i))
            out.append(
                {
                    "id": readable_id,
                    "title": title,
                    "url": url,
                    "published_at": published_at,
                }
            )
        return out

    # Phase 13 硬约束: 不再实现 _fallback()。所有源失败时 collect()
    # 直接返回 [], UI 显示"该分类暂无可用资讯"。
    # 真实链接优先于"假装有数据" — 详细约束见 SPEC §3。

    # Phase 11 延迟实现: 如遇到反爬, collect() 返回空并记录 warning。
    # 这是预期行为, 不需要额外处理逻辑。


__all__ = ["GDELT_SOURCES", "GDELTCollector"]
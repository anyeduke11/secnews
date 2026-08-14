"""OSS Insight 开源项目趋势采集器（Phase 11 延迟实现）。

继承 :class:`BaseCollector`：

- ``category``  : ``Category.TECH``  (开源技术趋势)
- ``sources``   : OSS Insight (开源项目趋势站点)
- ``timeout``   : 20s

Phase 11 延迟实现: 如果遇到反爬，collect() 返回空并记录 warning。
Phase 13 硬约束: 不实现 _fallback()，所有源失败时直接返回 []。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.collectors.base import BaseCollector
from backend.collectors.id_factory import make_readable_id
from backend.domain.enums import Category
from backend.domain.models import HotspotItem

OSSINSIGHT_SOURCES: list[dict] = [
    {
        "name": "OSSInsight",
        "url": "https://ossinsight.io/",
        "score": 77,
        "keywords": ["open source", "trends", "github"],
    },
]


class OSSInsightCollector(BaseCollector):
    """OSS Insight 开源项目趋势采集器。

    OSS Insight (https://ossinsight.io/) 是开源项目趋势分析平台，
    展示 GitHub 开源项目的活跃度、Star 增长、Pull Request 等趋势数据。

    Phase 11 延迟实现: 使用 HTML 解析提取页面内容。
    如遇到反爬，collect() 返回空并记录 warning。
    """

    category = Category.TECH
    sources = OSSINSIGHT_SOURCES
    timeout = 20

    def _build_items(
        self, raw_items: list[dict[str, Any]], source: dict
    ) -> list[HotspotItem]:
        """重写 _build_items 使用可读 ID 格式 ossinsight:trend:{id}。

        Phase 11: 新 collector 使用 readable_id 作为 HotspotItem.id，
        格式为 ``make_readable_id("ossinsight", "trend", str(i))``。
        """
        now = datetime.now(timezone.utc)
        items: list[HotspotItem] = []
        for i, raw in enumerate(raw_items):
            title = (raw.get("title") or "").strip()
            url = (raw.get("url") or "").strip()
            if not title or not url:
                continue
            readable_id = make_readable_id("ossinsight", "trend", str(i))
            items.append(
                HotspotItem(
                    id=readable_id,
                    title=title,
                    source=source["name"],
                    url=url,
                    category=self.category,
                    published_at=now,
                    fetched_at=now,
                    ingested_at=now,
                    score=source.get("score", 75),
                    is_fallback=False,
                    quality_score=100,
                    quality_flags=[],
                    url_check_status="pending",
                )
            )
        return items


__all__ = ["OSSINSIGHT_SOURCES", "OSSInsightCollector"]
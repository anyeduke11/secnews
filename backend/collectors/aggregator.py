# DEPRECATED: use backend.services.collection_service.CollectionService
# Kept for backward compatibility; will be removed in Phase 4.
#
# 热点数据聚合器 (v3)
# 整合所有数据源 + 生成趋势数据
#
# Phase 3 Task 7: 这个类已改造为薄兼容层，委托给
# :class:`backend.services.collection_service.CollectionService` 执行
# 实际的采集工作；本类只负责把 ``CollectionReport`` 转回 main.py
# 老 API 依赖的 ``{items, categoryCounts, total, trends, fetchedAt}``
# dict 格式。

import asyncio
from datetime import datetime, timezone


class HotspotAggregator:
    """DEPRECATED 兼容层：委托给 CollectionService

    旧 ``backend/main.py`` 的 ``/api/hotspots`` / ``/api/trends`` 等端点
    仍然走 ``cache_data.json`` → ``aggregator.collect_all()`` 路径。
    真正的采集逻辑由 :class:`CollectionService` 提供；本类只做格式
    转换。
    """

    def __init__(self):
        from backend.services.collection_service import CollectionService
        self._service = CollectionService()

    async def collect_all(self) -> dict:
        """委托给 CollectionService.run_once，转换为旧 dict 格式

        旧 main.py 期望的 schema::

            {
                "items": [<dict with id/title/summary/source/url/
                           category/publishedAt/score>],
                "categoryCounts": {"ai": n, "security": n, ...},
                "total": int,
                "trends": [<24h bucket dict>],   # 旧自包含；新版本返回 []
                "fetchedAt": iso8601,
            }
        """
        report = await self._service.run_once()

        all_items: list[dict] = []
        category_counts: dict[str, int] = {}
        for r in report.results:
            for item in r.items:
                # item is now a HotspotItem Pydantic model
                all_items.append({
                    "id": item.id,
                    "title": item.title,
                    "summary": item.summary,
                    "source": item.source,
                    "url": str(item.url),
                    "category": r.category.value,
                    "publishedAt": item.published_at.isoformat() if item.published_at else None,
                    "score": item.score or 0,
                })
            category_counts[r.category.value] = r.item_count

        return {
            "items": all_items,
            "categoryCounts": category_counts,
            "total": report.total,
            "trends": [],  # 趋势由 TrendRepository 接管
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
        }

    def get_top_items(self, items, n=50):
        scored = sorted(items, key=lambda x: x.get("score", 0), reverse=True)
        return scored[:n]

    def _generate_trends(self, items):
        return []  # 趋势由 TrendRepository 接管


__all__ = ["HotspotAggregator"]

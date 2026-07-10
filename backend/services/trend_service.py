"""Phase 4 TrendService — 24h 趋势数据 + 类别趋势。"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Optional

from backend.cache import list_cache
from backend.domain.enums import Category
from backend.repository.trend_repo import TrendRepository

_trepo = TrendRepository()


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


class TrendService:
    """业务编排：cache → repository。"""

    DEFAULT_HOURS = 24

    # ------------------------------------------------------------------
    def get_trends(self, hours: int = DEFAULT_HOURS) -> dict:
        """返回 ``{trends: [...], hours, fetched_at}`` 列表形态。

        ``trends`` 列表每项 ``{label, hours_ago, <每类 count>, total}``:
        - 包含每个 Category 的 count(ai/security/finance/startup/bid/github)
          便于前端 BarChart 堆叠展示。
        - ``total`` 为该小时桶的跨类别求和(为保持向后兼容保留)。
        """
        # 升级 cache_key 避免旧形状(只有 total)命中。
        cache_key = f"trends:{hours}h:v2"
        if cache_key in list_cache:
            return list_cache[cache_key]

        points = _trepo.get_current()

        # 跨类别求和 + 每类分别累计
        per_hour: dict[int, int] = defaultdict(int)
        per_hour_cat: dict[int, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        for p in points:
            per_hour[p.hours_ago] += p.count
            per_hour_cat[p.hours_ago][p.category] = p.count

        category_values = [c.value for c in Category]

        # 取最近 hours 桶(如果不足补 0)
        trends = []
        for h in range(hours):
            cat_counts = per_hour_cat.get(h, {})
            row: dict = {
                "label": f"-{h}h",
                "hours_ago": h,
                "total": per_hour.get(h, 0),
            }
            for cat in category_values:
                row[cat] = cat_counts.get(cat, 0)
            trends.append(row)

        result = {
            "version": "1.2.0",
            "hours": hours,
            "trends": trends,
            "fetched_at": _now_iso(),
        }
        list_cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    def get_category_trends(self, hours: int = DEFAULT_HOURS) -> dict:
        """返回 ``{category: [{label, hours_ago, count}, ...]}`` 形态。"""
        cache_key = f"trends:categories:{hours}h"
        if cache_key in list_cache:
            return list_cache[cache_key]

        points = _trepo.get_current()
        by_cat: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        for p in points:
            by_cat[p.category][p.hours_ago] = p.count

        result: dict = {
            "version": "1.2.0",
            "hours": hours,
            "data": {
                cat.value: [
                    {
                        "label": f"-{h}h",
                        "hours_ago": h,
                        "count": by_cat[cat.value].get(h, 0),
                    }
                    for h in range(hours)
                ]
                for cat in Category
            },
            "fetched_at": _now_iso(),
        }
        list_cache[cache_key] = result
        return result


__all__ = ["TrendService"]

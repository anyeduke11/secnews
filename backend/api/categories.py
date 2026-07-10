"""Phase 4 /api/categories router.

返回分类元数据：label / color / count。
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Query

from backend.cache import static_cache
from backend.domain.enums import Category, TimeRange
from backend.services.hotspot_service import HotspotService

router = APIRouter(prefix="/api/categories", tags=["categories"])

_LABELS: dict[str, str] = {
    "ai": "科技 / AI",
    "security": "网络安全",
    "finance": "金融 / 投资",
    "startup": "独立开发 / 创业",
    "bid": "招标资讯",
    "github": "GitHub / 开源",
}
_COLORS: dict[str, str] = {
    "ai": "#00bcd4",
    "security": "#e85d5d",
    "finance": "#f0c929",
    "startup": "#7c6aff",
    "bid": "#e8891a",
    "github": "#8b5cf6",
}


@router.get("")
async def list_categories(time_range: str = Query(default="7d")):
    """返回 5 个分类 + count。Phase 9 修复：同步 DB query 放 thread pool。

    Phase 35: ``Category.TECH`` 不再出现在响应中 — DB 仍用 ``tech``
    采集原始条目,但 ``count_by_category()`` 在 SQL 层已合并到 ``ai``,
    UI 也不再有独立「tech」tab。响应中保留 ``tech`` 字段会干扰前端
    CATEGORIES 渲染,这里用 set 排除。

    Phase 40: 接受 ``time_range`` query 参数 (默认 7d), 与 /api/hotspots
    的 category_counts 口径保持一致; 切换时间窗后会拿到对应窗口的分类计数。
    """
    try:
        tr = TimeRange(time_range)
    except ValueError as e:
        tr = TimeRange.D7  # 兜底: 无效输入按 7d 处理, 不阻断响应

    cache_key = f"categories:all:{tr.value}"
    if cache_key in static_cache:
        return static_cache[cache_key]
    counts = await asyncio.to_thread(HotspotService().count_by_category, tr)
    # Phase 35: 排除已合并的 tech (输出中不再出现)
    visible_cats = [c for c in Category if c.value != "tech"]
    result = {
        "version": "1.2.0",
        "time_range": tr.value,
        "categories": [
            {
                "id": c.value,
                "label": _LABELS.get(c.value, c.value),
                "color": _COLORS.get(c.value, "#888"),
                "count": counts.get(c.value, 0),
            }
            for c in visible_cats
        ],
        "fetched_at": datetime.utcnow().isoformat() + "Z",
    }
    static_cache[cache_key] = result
    return result

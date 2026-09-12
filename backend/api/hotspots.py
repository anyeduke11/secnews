"""Phase 4 /api/hotspots router."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from backend.logging_config import logger
from backend.services.hotspot_service import HotspotService

router = APIRouter(prefix="/api/hotspots", tags=["hotspots"])
_service = HotspotService()


def _load_interest_domains() -> list[str]:
    """DEV-0176 T0.4: 读兴趣画像 (settings.kv)。审计 P1-1 修复:

    同步 sqlite 读放 thread pool 调用; settings 表异常时降级为无画像
    (boost=None), 绝不让主 feed 端点因画像读取失败而 500。
    """
    try:
        from backend.repository.settings_repo import SettingsRepository

        interests = SettingsRepository().get("interest.practice_domains", [])
        if isinstance(interests, list):
            return [d for d in interests if isinstance(d, str)]
        return []
    except Exception as e:
        logger.warning(f"interest.practice_domains read failed, boost disabled: {e}")
        return []


@router.get("")
async def list_hotspots(
    category: str = Query("all", description="分类筛选，all 或具体值"),
    time_range: str = Query("7d", description="时间范围: 24h / 3d / 7d / 30d (7d 为本周周一 00:00 起, 非滚动 7 天)"),
    cursor: str = Query("", description="游标分页（首次为空）"),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    keyword: str = Query("", description="关键词搜索"),
    source: str = Query("", description="v1.9.1: 来源筛选（精确匹配 source 字段）"),
    exclude_category: str = Query("", description="DEV-0175: 排除单一分类（工作台聚焦裁决，前端默认传 bid）"),
    tags: str = Query("", description="v1.7: 逗号分隔 tag id, 触发标签筛选"),
    tag_mode: str = Query("or", pattern="^(and|or)$", description="v1.7: 标签筛选模式"),
):
    """列表查询（cursor 分页）。

    Phase 9 修复：同步 DB query 放 thread pool，避免 cache miss 时阻塞 event loop。
    v1.7 Phase 1: 新增 tags/tag_mode 标签筛选 (AND/OR), 传入 tags 时走 list_by_tags。
    DEV-0175: 新增 exclude_category (工作台聚焦, 前端默认排除 bid; 不传时行为与
    既有版本完全一致)。
    DEV-0178: 移除 region 参数与 /regions 端点 (标讯剔除, DB 列保留只读)。
    """
    tag_ids = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    if tag_ids:
        return await asyncio.to_thread(
            _service.list_by_tags, tag_ids, tag_mode, limit
        )
    # DEV-0176 T0.4: 兴趣画像从 settings.kv 单一来源读取 (前端不必回传)。
    # 空画像/读取失败 → boost=None, 排序行为与既有版本完全一致。
    boost = await asyncio.to_thread(_load_interest_domains)
    return await asyncio.to_thread(
        _service.list_hotspots,
        category=category,
        time_range=time_range,
        cursor=cursor or None,
        limit=limit,
        keyword=keyword,
        source=source or None,
        exclude_category=exclude_category or None,
        boost_practice_domains=boost or None,
    )


@router.get("/{item_id}")
async def get_hotspot(item_id: str):
    """单 item 详情。Phase 9 修复：同步 DB query 放 thread pool。"""
    return await asyncio.to_thread(_service.get_hotspot, item_id)

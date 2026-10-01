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
    # DEV-0182: 兴趣引擎连续乘子 (gate 开启且有行为/勾选信号时非空)。
    # 乘子表非空时优先于显式 boost (S 已融合 E, 是 boost 的超集); 空表时
    # 回退显式 boost 二值路径, 两种路径都保证无信号时排序 = 现状。
    boost_map: dict[str, float] | None = None
    try:
        from backend.extensions import is_extension_enabled

        if is_extension_enabled("interest_engine"):
            from backend.services.interest_engine_service import InterestEngineService

            boost_map = await asyncio.to_thread(InterestEngineService().get_boost_map)
    except Exception as e:
        logger.warning(f"interest boost map unavailable, fallback to explicit profile: {e}")
        boost_map = None
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
        practice_multiplier=boost_map,
    )


@router.get("/picked")
async def list_picked_hotspots(
    days: int = Query(2, ge=1, le=7, description="回溯天数"),
    limit: int = Query(30, ge=1, le=50, description="Top-N 条数"),
):
    """精选资讯 Top-N (P2 2026-09-27): pick_score DESC, pick_service 每轮落列。

    注意: 必须注册在 /{item_id} 之前, 否则 "picked" 会被吞成 item_id。
    Phase 9 同款: 同步 DB 查询放 thread pool。
    """
    items = await asyncio.to_thread(_service.list_picked, days, limit)
    return {"count": len(items), "items": items}


@router.get("/{item_id}")
async def get_hotspot(item_id: str):
    """单 item 详情。Phase 9 修复：同步 DB query 放 thread pool。"""
    return await asyncio.to_thread(_service.get_hotspot, item_id)

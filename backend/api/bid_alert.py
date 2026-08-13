"""Phase 4: 标书提醒与竞品分析 API (/api/bid-alert/*).

提供标书摘要、竞品分析、推荐标讯等用于行动层投标提醒面板的数据。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query

from backend.repository.db import get_connection

router = APIRouter(prefix="/api/bid-alert", tags=["bid-alert"])


def _fetch_bid_items(limit: int = 1000) -> list[dict[str, Any]]:
    """从 hotspots 表获取标讯类数据。"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, title, category, source, url, published_at, fetched_at,
               region, bid_status
        FROM hotspots
        WHERE category = 'bid'
        ORDER BY COALESCE(published_at, fetched_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/summary")
async def bid_summary():
    """标书摘要：今日新增、总开放数、地区分布、状态分布。"""
    items = _fetch_bid_items(2000)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    region_dist: dict[str, int] = {}
    status_dist: dict[str, int] = {}
    new_today = 0
    total_open = 0

    for item in items:
        pub = item.get("published_at") or item.get("fetched_at") or ""
        if pub.startswith(today):
            new_today += 1

        # 统计开放中的标讯
        status = item.get("bid_status") or "未知"
        if status in ("open", "招标", "公告", "报名中", "未知"):
            total_open += 1

        region = item.get("region") or "未知"
        region_dist[region] = region_dist.get(region, 0) + 1
        status_dist[status] = status_dist.get(status, 0) + 1

    return {
        "new_today": new_today,
        "total_open": total_open,
        "total_all": len(items),
        "region_distribution": region_dist,
        "status_distribution": status_dist,
        "summary_date": today,
    }


@router.get("/competitors")
async def competitor_analysis(
    limit: int = Query(500, ge=50, le=2000, description="分析的数据量"),
    top_n: int = Query(10, ge=3, le=30, description="返回的热词数"),
):
    """竞品分析：从标讯标题中提取高频关键词，识别竞品热点。

    基于标题分词 + 停用词过滤，统计竞争关键词出现频率。
    """
    items = _fetch_bid_items(limit)

    # 简单分词: 按常见分隔符拆分 + 过滤短词/停用词
    stop_words = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
        "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
        "们", "那", "些", "之", "与", "及", "或", "等", "招标", "公告",
        "项目", "采购", "工程", "服务", "2025", "2026", "第", "号",
    }

    word_count: dict[str, int] = {}
    for item in items:
        title = item.get("title") or ""
        # 按空白/标点拆分为词
        for sep in (" ", "，", "、", "。", "：", "；", "（", "）", "/", "-", "—"):
            title = title.replace(sep, " ")
        words = [w.strip() for w in title.split() if len(w.strip()) >= 2]
        for w in words:
            if w.lower() not in stop_words and not w.isdigit():
                word_count[w] = word_count.get(w, 0) + 1

    # 排序取 top_n
    sorted_words = sorted(word_count.items(), key=lambda x: -x[1])
    top_keywords = [{"keyword": k, "count": c} for k, c in sorted_words[:top_n]]

    # 按地区聚合
    region_dist: dict[str, int] = {}
    for item in items:
        region = item.get("region") or "未知"
        region_dist[region] = region_dist.get(region, 0) + 1

    return {
        "total_items": len(items),
        "top_keywords": top_keywords,
        "region_distribution": region_dist,
        "analysis_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


@router.get("/recent")
async def recent_bids(
    limit: int = Query(20, ge=5, le=100, description="返回条数"),
):
    """最近标讯：用于行动层投标提醒面板的最近标讯列表。"""
    items = _fetch_bid_items(limit)
    return {
        "items": [
            {
                "id": item["id"],
                "title": item["title"],
                "source": item.get("source"),
                "url": item.get("url"),
                "region": item.get("region"),
                "bid_status": item.get("bid_status"),
                "published_at": item.get("published_at") or item.get("fetched_at"),
            }
            for item in items
        ],
        "total": len(items),
    }
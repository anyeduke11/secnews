"""GET /api/kl/compounding — 复利仪表盘聚合指标 (Phase 13, P3-5 修复)。

Batch 2 D (api 层 SQL 下沉): 全部聚合 SQL + 30s TTL 缓存在
``backend/services/wiki_stats_service.compounding_snapshot``; 本文件只留路由。

P3-5 (2026-08-16) 修复的三处空转数据源 (口径记录, 实现在 service):
1. avg_score 原取 AVG(mastery) (全 0) → 改为 AVG(attention_score)
   (注意力事件经 P3-2 前端埋点流入, attention_aggregate job 聚合)
2. trigger_health 原读进程内内存计数器 (重启清零) → 改为读 kl_dead_letters
   表 (持久化) + 进程内计数合并
3. top_concepts 原 join knowledge_links×concepts (links/concepts 稀疏)
   → 改为直接聚合 knowledge_items.concepts 列
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/kl", tags=["kl"])


@router.get("/compounding")
def get_compounding() -> dict:
    """Return compounding metrics for the knowledge dashboard.

    Returns
    -------
    daily_trend
        items ingested per day (last 30d) with count and avg attention score
    weekly_trend
        items per week (last 12w) with count and avg attention score
    monthly_trend
        items per month (last 6m) with count and avg attention score
    top_concepts
        top 10 concepts by item participation (name + score)
    trigger_health
        T1-T4 dead-letter counts (persisted in kl_dead_letters) + 进程内计数
    stage_distribution
        count of items per lifecycle stage
    """
    from backend.services.wiki_stats_service import compounding_snapshot

    return compounding_snapshot()


__all__ = ["router"]

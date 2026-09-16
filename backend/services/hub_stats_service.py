"""UI 收尾批 C3 (DEV-0191) — 资料库前厅聚合统计 (hub-stats)。

单一只读端点 ``GET /api/knowledge/hub-stats`` 的数据源聚合 (方案 DD-6:
不落缓存表, 全只读逐源容错 — 单源失败置 None, 不拖垮整个响应)。

聚合口径 (全部复用既有服务/仓库, 不新建表):
- wiki_items        knowledge_repo.count_items()               全库编目条目
- wiki_chunks       knowledge_chunks 表 COUNT (migration 054)   chunk 总量
- review_total/due  review_service.stats() (SM-2)               复习在册/到期
- funnel_total      wiki_stats_service.funnel_from_db()         管线漏斗合计
- queue_pending     kl_pipeline 队列 (kl_queue_table)           队列待处理
- quality_24h       QualityLogRepository.summary_24h()          24h 门禁检查合计

前端消费: /knowledge/khub (KnowledgeHubPage)。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.repository.knowledge_repo import knowledge_repo


def _wiki_chunks_count() -> int:
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()
    return int(row[0]) if row else 0


def _safe(label: str, fn: Any) -> Any:
    """逐源容错: 单源异常置 None (前端显示 …), 不拖垮聚合响应。"""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — 聚合器对单源故障免疫
        logger.warning(f"hub_stats source '{label}' failed: {e}")
        return None


def hub_stats() -> dict[str, Any]:
    """聚合六源统计 (同步函数, 路由层经 to_thread 调用)。"""
    # 1) 编目条目
    wiki_items = _safe("wiki_items", lambda: knowledge_repo.count_items())

    # 2) chunk 总量
    wiki_chunks = _safe("wiki_chunks", _wiki_chunks_count)

    # 3) 复习 (SM-2): 在册 + 到期
    def _reviews() -> tuple[int, int]:
        from backend.services.review_service import stats as review_stats

        s = review_stats()
        return int(s.get("total", 0)), int(s.get("due", 0))

    reviews = _safe("reviews", _reviews)
    review_total, review_due = reviews if reviews else (None, None)

    # 4) 管线漏斗合计 (DB knowledge_items.lifecycle 口径)
    def _funnel_total() -> int:
        from backend.services.wiki_stats_service import funnel_from_db

        return sum(int(f.get("count") or 0) for f in funnel_from_db())

    funnel_total = _safe("funnel", _funnel_total)

    # 5) 队列待处理 (kl_queue_table)
    def _queue_pending() -> int:
        from backend.kl_pipeline.runtime import get_production_pipeline

        q = get_production_pipeline().queue.stats()
        return int(q.get("pending", 0))

    queue_pending = _safe("queue", _queue_pending)

    # 6) 24h 门禁检查合计 (各 gate pass+fail)
    def _quality_24h() -> int:
        from backend.repository.quality_repo import QualityLogRepository

        summary = QualityLogRepository().summary_24h()
        return sum(
            int(g.get("total") or (int(g.get("pass_n") or 0) + int(g.get("fail_n") or 0)))
            for g in summary.values()
        )

    quality_24h = _safe("quality", _quality_24h)

    return {
        "wiki_items": wiki_items,
        "wiki_chunks": wiki_chunks,
        "review_total": review_total,
        "review_due": review_due,
        "funnel_total": funnel_total,
        "queue_pending": queue_pending,
        "quality_checked_24h": quality_24h,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


__all__ = ["hub_stats"]

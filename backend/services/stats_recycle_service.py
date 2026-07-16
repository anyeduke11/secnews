"""Stats recycle service — fetch published article stats daily.

Phase 1f Task 6.9: 每日 06:00 扫描 content_calendar 中已发布条目，
尝试从平台 API 拉取阅读/点赞数据。当前阶段平台 API 未接入，
降级为仅 log，不阻断。
"""
from __future__ import annotations

import logging

from backend.repository.db import get_connection

log = logging.getLogger("hotspot.stats_recycle")


def recycle_stats() -> dict:
    """Fetch stats for published articles.

    Queries content_calendar for entries with published_url, attempts to
    fetch stats (views/likes) from platform APIs. Falls back gracefully
    when platform APIs are unavailable.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, published_url, platform FROM content_calendar "
        "WHERE published_url IS NOT NULL"
    ).fetchall()

    recycled = 0
    skipped = 0
    for row in rows:
        url = row["published_url"]
        # 降级处理：平台 API 需要认证，当前只 log
        log.info(f"would fetch stats for: {url}")
        skipped += 1

    log.info(
        f"stats recycle: {recycled} updated, {skipped} skipped (no platform API)"
    )
    return {"recycled": recycled, "skipped": skipped}

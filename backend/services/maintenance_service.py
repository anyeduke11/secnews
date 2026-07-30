"""Data maintenance service — cleanup, vacuum, and health check.

Usage:
    POST /api/maintenance/vacuum     — VACUUM + reindex
    POST /api/maintenance/cleanup    — 清理 >30 天历史数据 (dry_run 参数预览)
    GET  /api/maintenance/health     — DB 大小、碎片率等
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from backend.repository.db import get_connection

log = logging.getLogger("hotspot.maintenance")

# 默认清理阈值
DEFAULT_HISTORY_DAYS = 90


# ---------------------------------------------------------------------------
# DB size / health
# ---------------------------------------------------------------------------

def db_health() -> dict:
    """Return DB file size, page count, and journal mode."""
    conn = get_connection()
    try:
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        freelist_count = conn.execute("PRAGMA freelist_count").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    except Exception as e:
        log.warning(f"db_health pragma failed: {e}")
        page_count = page_size = freelist_count = 0
        journal_mode = "unknown"

    db_path = Path(os.environ.get("HOTSPOT_DB_PATH", "backend/hotspot.db"))
    size_bytes = db_path.stat().st_size if db_path.exists() else 0

    return {
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / 1024 / 1024, 2),
        "page_count": page_count,
        "page_size": page_size,
        "freelist_pages": freelist_count,
        "fragmentation_pct": round(freelist_count / max(page_count, 1) * 100, 1),
        "journal_mode": journal_mode,
        "db_path": str(db_path),
    }


def run_vacuum() -> dict:
    """VACUUM + reindex + analyze. Returns timing stats."""
    conn = get_connection()
    start = time.time()

    conn.execute("VACUUM")
    vac_time = time.time() - start

    start2 = time.time()
    conn.execute("REINDEX")
    reindex_time = time.time() - start2

    start3 = time.time()
    conn.execute("ANALYZE")
    analyze_time = time.time() - start3

    health = db_health()
    return {
        "status": "ok",
        "vacuum_seconds": round(vac_time, 3),
        "reindex_seconds": round(reindex_time, 3),
        "analyze_seconds": round(analyze_time, 3),
        "total_seconds": round(vac_time + reindex_time + analyze_time, 3),
        "health": health,
    }


# ---------------------------------------------------------------------------
# Data cleanup
# ---------------------------------------------------------------------------

def cleanup_history(
    days: int = DEFAULT_HISTORY_DAYS,
    dry_run: bool = True,
) -> dict:
    """Delete old records from sync_history and hotspot_history.

    Args:
        days: 保留最近 N 天的记录
        dry_run: True 只预览, False 实际删除

    Returns:
        {"dry_run": bool, "deleted": {表名: 行数}}
    """
    import json
    from datetime import datetime, timedelta, timezone

    conn = get_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    results: dict[str, int] = {}

    # sync_history
    rows = conn.execute(
        "SELECT COUNT(*) FROM sync_history WHERE finished_at < ?", (cutoff,)
    ).fetchone()[0]
    if rows > 0:
        if not dry_run:
            conn.execute(
                "DELETE FROM sync_history WHERE finished_at < ?", (cutoff,)
            )
        results["sync_history"] = rows

    # hotspot_history / collection_history
    for table in ("collection_history", "hotspot_history"):
        try:
            rows = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE ingested_at < ?", (cutoff,)
            ).fetchone()[0]
            if rows > 0:
                if not dry_run:
                    conn.execute(
                        f"DELETE FROM {table} WHERE ingested_at < ?", (cutoff,)
                    )
                results[table] = rows
        except Exception:
            pass  # table may not exist

    # export_cache (HTTP 缓存)
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM export_cache WHERE cached_at < ?", (cutoff,)
        ).fetchone()[0]
        if rows > 0:
            if not dry_run:
                conn.execute(
                    "DELETE FROM export_cache WHERE cached_at < ?", (cutoff,)
                )
            results["export_cache"] = rows
    except Exception:
        pass

    return {
        "dry_run": dry_run,
        "retention_days": days,
        "cutoff": cutoff,
        "deleted": results,
        "total_rows": sum(results.values()),
    }


# ---------------------------------------------------------------------------
# knowledge items orphan detection
# ---------------------------------------------------------------------------

def detect_orphan_items() -> dict:
    """Find orphaned knowledge items (no concepts, no domain classification)."""
    from backend.repository.knowledge_repo import knowledge_repo

    items = knowledge_repo.list_items(limit=10000)
    no_domain = [i for i in items if not i.domain]
    no_concepts = [i for i in items if not i.concepts]

    return {
        "total_items": len(items),
        "no_domain": len(no_domain),
        "no_concepts": len(no_concepts),
        "orphan_items": len(no_domain) + len(no_concepts),  # may overlap
    }


__all__ = [
    "db_health",
    "run_vacuum",
    "cleanup_history",
    "detect_orphan_items",
]
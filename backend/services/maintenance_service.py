"""Data maintenance service — cleanup, vacuum, and health check.

Usage:
    POST /api/maintenance/vacuum                 — VACUUM + reindex
    POST /api/maintenance/cleanup                — 清理 >30 天历史数据 (dry_run 参数预览)
    GET  /api/maintenance/health                 — DB 大小、碎片率等
    GET  /api/maintenance/table-stats            — 每表行数/大小分析
    POST /api/maintenance/cleanup-quality-logs   — 清理 quality_check_logs
    GET  /api/maintenance/duplicates             — 检测重复数据
    POST /api/maintenance/cleanup-duplicates     — 清理重复数据
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
DEFAULT_QUALITY_LOG_DAYS = 7


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


# ---------------------------------------------------------------------------
# Detailed table statistics
# ---------------------------------------------------------------------------

def table_stats() -> list[dict]:
    """Return per-table row count, column count, and estimated size contribution."""
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    results = []
    for (t,) in tables:
        if t.startswith("sqlite_") or any(
            t.endswith(sfx) for sfx in ("_fts", "_fts_data", "_fts_idx", "_fts_content", "_fts_docsize", "_fts_config")
        ):
            continue
        cols = conn.execute(f'PRAGMA table_info("{t}")').fetchall()
        row_count = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        est_size = row_count * len(cols) * 32  # rough estimate in bytes
        results.append({
            "table": t,
            "rows": row_count,
            "columns": len(cols),
            "estimated_mb": round(est_size / 1024 / 1024, 3),
        })
    return results


# ---------------------------------------------------------------------------
# quality_check_logs cleanup
# ---------------------------------------------------------------------------

def cleanup_quality_logs(
    days: int = DEFAULT_QUALITY_LOG_DAYS,
    dry_run: bool = True,
) -> dict:
    """Delete old quality_check_logs entries.

    quality_check_logs accumulates ~3M rows/month.  Only the last N days
    are useful for debugging; everything older can be safely purged.
    """
    from datetime import datetime, timedelta, timezone

    conn = get_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Total rows
    total = conn.execute("SELECT COUNT(*) FROM quality_check_logs").fetchone()[0]

    # Rows to delete
    to_delete = conn.execute(
        "SELECT COUNT(*) FROM quality_check_logs WHERE checked_at < ?", (cutoff,)
    ).fetchone()[0]

    # Breakdown by month
    monthly = {}
    for row in conn.execute(
        "SELECT substr(checked_at,1,7) as m, COUNT(*) FROM quality_check_logs "
        "WHERE checked_at < ? GROUP BY m ORDER BY m", (cutoff,)
    ).fetchall():
        monthly[row[0]] = row[1]

    if not dry_run and to_delete > 0:
        conn.execute(
            "DELETE FROM quality_check_logs WHERE checked_at < ?", (cutoff,)
        )
        log.info(f"cleanup_quality_logs: deleted {to_delete} rows older than {cutoff}")

    return {
        "dry_run": dry_run,
        "retention_days": days,
        "cutoff": cutoff,
        "total_rows_before": total,
        "rows_to_delete": to_delete,
        "rows_remaining_after": total - to_delete,
        "monthly_breakdown": monthly,
    }


# ---------------------------------------------------------------------------
# Duplicate detection & cleanup
# ---------------------------------------------------------------------------

def detect_duplicate_hotspots() -> list[dict]:
    """Find duplicate hotspots by URL (same URL, multiple IDs)."""
    conn = get_connection()
    results = []
    rows = conn.execute(
        "SELECT url, COUNT(*) as cnt, GROUP_CONCAT(id) as ids "
        "FROM hotspots WHERE url != '' GROUP BY url HAVING cnt > 1 "
        "ORDER BY cnt DESC LIMIT 50"
    ).fetchall()
    for url, cnt, ids in rows:
        results.append({
            "url": url,
            "count": cnt,
            "ids": ids.split(","),
        })
    return results


def detect_duplicate_knowledge_items() -> list[dict]:
    """Find duplicate knowledge items by title."""
    conn = get_connection()
    results = []
    rows = conn.execute(
        "SELECT title, COUNT(*) as cnt, GROUP_CONCAT(id) as ids "
        "FROM knowledge_items WHERE title != '' GROUP BY title HAVING cnt > 1 "
        "ORDER BY cnt DESC LIMIT 50"
    ).fetchall()
    for title, cnt, ids in rows:
        results.append({
            "title": title,
            "count": cnt,
            "ids": ids.split(","),
        })
    return results


def cleanup_duplicate_hotspots(dry_run: bool = True) -> dict:
    """Deduplicate hotspots by keeping the earliest-inserted row per URL.

    Deletes all but the first (lowest rowid) entry for each duplicate URL.
    """
    conn = get_connection()
    results: dict[str, int] = {}

    # Find duplicates & keep the first one
    dupes = conn.execute(
        "SELECT url, COUNT(*) as cnt FROM hotspots "
        "WHERE url != '' GROUP BY url HAVING cnt > 1"
    ).fetchall()

    to_delete = 0
    for url, cnt in dupes:
        ids = [
            r[0] for r in conn.execute(
                "SELECT id FROM hotspots WHERE url = ? ORDER BY ROWID ASC", (url,)
            ).fetchall()
        ]
        if len(ids) > 1:
            keep_id = ids[0]
            delete_ids = ids[1:]
            if not dry_run:
                placeholders = ",".join("?" for _ in delete_ids)
                conn.execute(
                    f"DELETE FROM hotspots WHERE id IN ({placeholders})",
                    delete_ids,
                )
                log.info(f"dedup hotspots: kept {keep_id}, deleted {len(delete_ids)} for URL {url[:60]}")
            to_delete += len(delete_ids)

    results["hotspots"] = to_delete

    # Recalculate tags after dedup
    if not dry_run and to_delete > 0:
        try:
            conn.execute("DELETE FROM hotspot_tags WHERE hotspot_id NOT IN (SELECT id FROM hotspots)")
        except Exception:
            pass

    return {
        "dry_run": dry_run,
        "deleted": results,
        "total_deleted": to_delete,
    }


def cleanup_duplicate_knowledge_items(dry_run: bool = True) -> dict:
    """Deduplicate knowledge items by keeping the earliest-inserted row per title.

    Deletes all but the first (lowest rowid) entry for each duplicate title.
    """
    conn = get_connection()
    results: dict[str, int] = {}

    dupes = conn.execute(
        "SELECT title, COUNT(*) as cnt FROM knowledge_items "
        "WHERE title != '' GROUP BY title HAVING cnt > 1"
    ).fetchall()

    to_delete = 0
    for title, cnt in dupes:
        ids = [
            r[0] for r in conn.execute(
                "SELECT id FROM knowledge_items WHERE title = ? ORDER BY ROWID ASC",
                (title,),
            ).fetchall()
        ]
        if len(ids) > 1:
            delete_ids = ids[1:]
            if not dry_run:
                placeholders = ",".join("?" for _ in delete_ids)
                conn.execute(
                    f"DELETE FROM knowledge_items WHERE id IN ({placeholders})",
                    delete_ids,
                )
                log.info(f"dedup knowledge_items: kept {ids[0]}, deleted {len(delete_ids)} for title {title[:60]}")
            to_delete += len(delete_ids)

    results["knowledge_items"] = to_delete
    return {
        "dry_run": dry_run,
        "deleted": results,
        "total_deleted": to_delete,
    }


# ---------------------------------------------------------------------------
# Comprehensive dirty-data report
# ---------------------------------------------------------------------------

def dirty_data_report() -> dict:
    """Generate a comprehensive report of all detected dirty / invalid data."""
    conn = get_connection()

    # quality_check_logs
    qcl_total = conn.execute("SELECT COUNT(*) FROM quality_check_logs").fetchone()[0]
    qcl_old = conn.execute(
        "SELECT COUNT(*) FROM quality_check_logs WHERE checked_at < "
        "(SELECT datetime('now', '-7 days'))"
    ).fetchone()[0]

    # Duplicate hotspots
    dup_hotspots = len(conn.execute(
        "SELECT COUNT(*) FROM hotspots WHERE url != '' "
        "GROUP BY url HAVING COUNT(*) > 1"
    ).fetchall())

    # Duplicate knowledge items
    dup_ki = len(conn.execute(
        "SELECT COUNT(*) FROM knowledge_items WHERE title != '' "
        "GROUP BY title HAVING COUNT(*) > 1"
    ).fetchall())

    # Orphaned raw_items
    orphan_raw = conn.execute(
        "SELECT COUNT(*) FROM raw_items WHERE item_id NOT IN (SELECT id FROM hotspots)"
    ).fetchone()[0]

    # Invalid URLs in hotspots
    invalid_urls = conn.execute(
        "SELECT COUNT(*) FROM hotspots WHERE url LIKE 'javascript:%' OR url = ''"
    ).fetchone()[0]

    return {
        "quality_check_logs": {
            "total": qcl_total,
            "older_than_7_days": qcl_old,
        },
        "duplicate_hotspots": dup_hotspots,
        "duplicate_knowledge_items": dup_ki,
        "orphan_raw_items": orphan_raw,
        "invalid_urls": invalid_urls,
    }


__all__ = [
    "db_health",
    "run_vacuum",
    "cleanup_history",
    "detect_orphan_items",
    "table_stats",
    "cleanup_quality_logs",
    "detect_duplicate_hotspots",
    "detect_duplicate_knowledge_items",
    "cleanup_duplicate_hotspots",
    "cleanup_duplicate_knowledge_items",
    "dirty_data_report",
]
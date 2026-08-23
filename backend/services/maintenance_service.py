"""Data maintenance service — cleanup, vacuum, and health check.

Usage:
    POST /api/maintenance/vacuum                 — VACUUM + reindex
    POST /api/maintenance/cleanup                — 清理 >30 天历史数据 (dry_run 参数预览)
    GET  /api/maintenance/health                 — DB 大小、碎片率等
    GET  /api/maintenance/table-stats            — 每表行数/大小分析
    POST /api/maintenance/cleanup-quality-logs   — 清理 quality_check_logs
    GET  /api/maintenance/duplicates             — 检测重复数据
    POST /api/maintenance/cleanup-duplicates     — 清理重复数据

方案 A (M2-T6 修订): 表位置由部署期迁移脚本 (scripts/migrate_temp_layers.py)
决定, 代码一律用裸表名 — SQLite 对未限定名称按 main → ATTACH 库顺序解析,
迁移后自动落到 warm.db, 读写永不分裂。
"""

from __future__ import annotations

import json
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
    from datetime import datetime, timedelta, timezone

    conn = get_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    results: dict[str, int] = {}

    # 方案 A: 裸表名 (跟随迁移后实际位置, SQLite 名称解析自动回退)
    sh = "sync_history"
    rows = conn.execute(
        f"SELECT COUNT(*) FROM {sh} WHERE finished_at < ?", (cutoff,)
    ).fetchone()[0]
    if rows > 0:
        if not dry_run:
            conn.execute(
                f"DELETE FROM {sh} WHERE finished_at < ?", (cutoff,)
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

def archive_quality_logs(
    days: int = DEFAULT_QUALITY_LOG_DAYS,
    dry_run: bool = True,
) -> dict:
    """将超过保留窗口的 quality_check_logs 归档到 archive 表。

    P0.1: 替代原直接 DELETE 策略。归档后数据可追溯 90 天,
    同时通过 incremental_vacuum 回收主表磁盘空间。

    Args:
        days: 主表保留天数 (默认 7 天)
        dry_run: True 只预览不实际移动

    Returns:
        dict with rows_to_archive, rows_archived, main_remaining, archive_total
    """
    from datetime import datetime, timedelta, timezone

    conn = get_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    # 方案 A: 裸表名 (跟随迁移后的实际位置, 见 _cleanup_old_data 注释)
    qcl = "quality_check_logs"

    # 统计待归档行数
    to_archive = conn.execute(
        f"SELECT COUNT(*) FROM {qcl} WHERE checked_at < ?", (cutoff,)
    ).fetchone()[0]

    # 主表当前总行数
    main_total = conn.execute(f"SELECT COUNT(*) FROM {qcl}").fetchone()[0]

    # 归档表当前总行数
    archive_total = conn.execute(
        "SELECT COUNT(*) FROM quality_check_logs_archive"
    ).fetchone()[0]

    if not dry_run and to_archive > 0:
        # 事务: 先归档再删除再回收空间
        conn.execute("BEGIN")
        try:
            conn.execute(
                "INSERT INTO quality_check_logs_archive "
                "(id, item_id, gate_name, passed, score_deduction, flags, "
                "reason, error_msg, checked_at, mode, archived_at) "
                "SELECT id, item_id, gate_name, passed, score_deduction, flags, "
                "reason, error_msg, checked_at, mode, ? "
                f"FROM {qcl} WHERE checked_at < ?",
                (now_iso, cutoff),
            )
            conn.execute(
                f"DELETE FROM {qcl} WHERE checked_at < ?", (cutoff,)
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        # 回收主表空间 (incremental_vacuum 需要 auto_vacuum=1, 否则降级为 VACUUM)
        try:
            auto_vacuum = conn.execute("PRAGMA auto_vacuum").fetchone()[0]
            if auto_vacuum == 1:
                conn.execute("PRAGMA incremental_vacuum(500)")
                log.info(f"archive_quality_logs: incremental_vacuum done")
            else:
                log.info(f"archive_quality_logs: auto_vacuum off, skip space reclaim")
        except Exception as e:
            log.warning(f"archive_quality_logs: vacuum failed (non-fatal): {e}")

        log.info(
            f"archive_quality_logs: archived {to_archive} rows older than {cutoff}, "
            f"main remaining {main_total - to_archive}"
        )

    main_remaining = conn.execute(
        f"SELECT COUNT(*) FROM {qcl}"
    ).fetchone()[0]
    archive_total_after = conn.execute(
        "SELECT COUNT(*) FROM quality_check_logs_archive"
    ).fetchone()[0]

    return {
        "dry_run": dry_run,
        "retention_days": days,
        "cutoff": cutoff,
        "rows_to_archive": to_archive,
        "rows_archived": 0 if dry_run else to_archive,
        "main_remaining": main_remaining,
        "archive_total": archive_total_after,
    }


def cleanup_quality_logs(
    days: int = DEFAULT_QUALITY_LOG_DAYS,
    dry_run: bool = True,
) -> dict:
    """清理 quality_check_logs (P0.1: 先归档再删除)。

    薄包装: 调用 archive_quality_logs, 保持 API 向后兼容。
    原 API 响应字段 (rows_to_delete 等) 保留, 新增 rows_archived。
    """
    result = archive_quality_logs(days=days, dry_run=dry_run)

    return {
        "dry_run": dry_run,
        "retention_days": days,
        "cutoff": result["cutoff"],
        "total_rows_before": result["main_remaining"] + result["rows_archived"],
        "rows_to_delete": result["rows_to_archive"],
        "rows_archived": result["rows_archived"],
        "rows_remaining_after": result["main_remaining"],
        "monthly_breakdown": {},  # P0.1: 不再需要月度明细 (归档表可查)
    }


# ---------------------------------------------------------------------------
# v0.5 §18 遥测窗口 (7 天滚动清理, WARM 层)
# ---------------------------------------------------------------------------

TELEMETRY_RETENTION_PATH = Path(__file__).resolve().parents[2] / "scripts" / "retention.json"
TELEMETRY_SCHEDULE_TAG = "telemetry_window"


def load_telemetry_specs(
    path: Path = TELEMETRY_RETENTION_PATH,
) -> list[dict]:
    """从 retention.json 台账取 ``scheduled_in == "telemetry_window"`` 的表规格。

    台账是唯一事实源 — 窗口天数/时间戳列/动作全部由台账声明,
    本函数只做筛选, 不复制任何策略常量。
    """
    specs = json.loads(path.read_text(encoding="utf-8")).get("tables", [])
    return [s for s in specs if s.get("scheduled_in") == TELEMETRY_SCHEDULE_TAG]


def run_telemetry_window(
    dry_run: bool = True,
    specs: list[dict] | None = None,
) -> dict:
    """SPEC §18「7 天遥测窗口」统一入口。

    按 retention.json 中 ``scheduled_in == "telemetry_window"`` 的声明
    逐表清理 WARM 层遥测表 (crawler_runs / raw_items truncate;
    quality_check_logs 走 archive_db_table)。每表独立 try/except 隔离,
    失败不阻塞后续表。

    复用 scripts.db_diet.cleanup_table 的单表执行器 (DRY), 避免第二份
    DELETE 语义; get_connection() 自动 ATTACH warm, 裸表名即可达。
    """
    from scripts.db_diet import cleanup_table

    if specs is None:
        specs = load_telemetry_specs()

    conn = get_connection()
    results: list[dict] = []
    for spec in specs:
        try:
            results.append(cleanup_table(conn, spec, dry_run=dry_run))
            conn.commit()  # 每表一提交: 释放写锁 (与 db_diet.run 相同理由)
        except Exception as e:
            results.append({
                "table": spec.get("table"),
                "action": spec.get("action"),
                "ok": False,
                "skipped_reason": f"exception: {type(e).__name__}: {e}",
            })

    return {
        "dry_run": dry_run,
        "window_days_tag": TELEMETRY_SCHEDULE_TAG,
        "tables": len(results),
        "rows_deleted": sum(r.get("deleted", 0) for r in results),
        "rows_archived": sum(r.get("archived", 0) for r in results),
        # 仅硬错误计为 failed (table_not_found 等 skipped 不告警)
        "failed": sum(
            1 for r in results
            if not r.get("ok") and not r.get("skipped_reason")
        ),
        "results": results,
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
    ki = "knowledge_items"
    results = []
    rows = conn.execute(
        f"SELECT title, COUNT(*) as cnt, GROUP_CONCAT(id) as ids "
        f"FROM {ki} WHERE title != '' GROUP BY title HAVING cnt > 1 "
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
    """Deduplicate hotspots to reduce storage (v4.4 增强: 保最高质量).

    - 分组键: ``canonicalize_url``（移除 www. / 丢弃 query / 去尾部斜杠），
      比旧实现「URL 全字面相等」覆盖更多真实重复。
    - 保留: 组内 ``quality_score`` 最高者；同分取 ``ROWID`` 最新（晚入库）。
      —— 从旧「保最早插入」改为「保最高质量」。
    - 纯内存分组后批量 DELETE，不引入新表。

    注意: 纯 SQL GROUP BY canonical 需 count 无法直接复用现有表达式，
    因此在 Python 侧按 canonical 分组（规模 ~3300 行, 无性能顾虑）。
    """
    from backend.quality.url_canonicalize import canonicalize_url

    conn = get_connection()
    results: dict[str, int] = {}

    # 读全量 id/title/url/quality/rowid（分组在内存做）
    rows = conn.execute(
        "SELECT id, url, quality_score, ROWID as _row FROM hotspots WHERE url != ''"
    ).fetchall()

    # 按 canonical url 分组
    groups: dict[str, list[tuple[str, int, int]]] = {}  # canon -> [(id, q, rowid)]
    for row in rows:
        _id, url, q, rid = row[0], row[1], row[2] or 0, row[3]
        try:
            canon = canonicalize_url(str(url))
        except Exception:
            canon = str(url)
        groups.setdefault(canon, []).append((_id, q, rid))

    to_delete = 0
    for canon, members in groups.items():
        if len(members) <= 1:
            continue
        # 保: quality_score 最高; 同分取 ROWID 最新(large)
        members_sorted = sorted(members, key=lambda m: (m[1], m[2]))
        keep_id = members_sorted[-1][0]
        delete_ids = [m[0] for m in members_sorted[:-1]]
        if not dry_run and delete_ids:
            placeholders = ",".join("?" for _ in delete_ids)
            conn.execute(
                f"DELETE FROM hotspots WHERE id IN ({placeholders})",
                delete_ids,
            )
            log.info(
                f"dedup hotspots: kept q{members_sorted[-1][1]} {keep_id[:36]}, "
                f"deleted {len(delete_ids)} for canon={canon[:60]}"
            )
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
    ki = "knowledge_items"
    results: dict[str, int] = {}

    dupes = conn.execute(
        f"SELECT title, COUNT(*) as cnt FROM {ki} "
        "WHERE title != '' GROUP BY title HAVING cnt > 1"
    ).fetchall()

    to_delete = 0
    for title, _cnt in dupes:
        ids = [
            r[0] for r in conn.execute(
                f"SELECT id FROM {ki} WHERE title = ? ORDER BY ROWID ASC",
                (title,),
            ).fetchall()
        ]
        if len(ids) > 1:
            delete_ids = ids[1:]
            if not dry_run:
                placeholders = ",".join("?" for _ in delete_ids)
                conn.execute(
                    f"DELETE FROM {ki} WHERE id IN ({placeholders})",
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
    qcl = "quality_check_logs"
    ki = "knowledge_items"
    ri = "raw_items"

    # quality_check_logs
    qcl_total = conn.execute(f"SELECT COUNT(*) FROM {qcl}").fetchone()[0]
    qcl_old = conn.execute(
        f"SELECT COUNT(*) FROM {qcl} WHERE checked_at < "
        "(SELECT datetime('now', '-7 days'))"
    ).fetchone()[0]

    # Duplicate hotspots
    dup_hotspots = len(conn.execute(
        "SELECT COUNT(*) FROM hotspots WHERE url != '' "
        "GROUP BY url HAVING COUNT(*) > 1"
    ).fetchall())

    # Duplicate knowledge items
    dup_ki = len(conn.execute(
        f"SELECT COUNT(*) FROM {ki} WHERE title != '' "
        "GROUP BY title HAVING COUNT(*) > 1"
    ).fetchall())

    # Orphaned raw_items
    orphan_raw = conn.execute(
        f"SELECT COUNT(*) FROM {ri} WHERE item_id NOT IN (SELECT id FROM hotspots)"
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
    "cleanup_duplicate_hotspots",
    "cleanup_duplicate_knowledge_items",
    "cleanup_history",
    "cleanup_quality_logs",
    "db_health",
    "detect_duplicate_hotspots",
    "detect_duplicate_knowledge_items",
    "detect_orphan_items",
    "dirty_data_report",
    "run_vacuum",
    "table_stats",
]
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
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.repository.db import get_connection, knowledge_items_table

log = logging.getLogger("hotspot.maintenance")

# 默认清理阈值
DEFAULT_HISTORY_DAYS = 90
# DEV-0322 三档模型: 保留窗口 = 3 档 × 档宽 7 天 (档宽唯一事实源 =
# retention.json qcl retention_days / 3; 本常数为无台账消费处的兜底)
DEFAULT_QUALITY_LOG_DAYS = 21
DEFAULT_QUALITY_LOG_TIERS = 3


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

def index_health(mode: str = "quick") -> dict:
    """索引健康探测 (DEV-0320): 逐 schema 如实返回可证实的索引状态。

    只采集 SQLite 能权威回答的三类信号, 不编造指标:
    - 索引计数: 用户索引 vs 系统 autoindex (sqlite_autoindex% 由 UNIQUE/PK
      约束派生, 不可独立 REINDEX, 分开展示避免误导)
    - 结构检查: ``PRAGMA <schema>.quick_check`` (默认, B-tree 页结构校验,
      毫秒~秒级) 或 ``integrity_check`` (mode="full", 含索引内容一致性,
      大库秒~分级) — 返回非 "ok" 行即问题清单, 如实带出
    - ANALYZE planner 统计: ``stat1_covered`` = 已进入 sqlite_stat1 的
      被索引表数。**不作覆盖率分母展示** — SQLite 3.32+ 起 ANALYZE 对
      <44 行小表与纯 autoindex 表有意不产统计 (实测 custom_sources 显式
      ANALYZE 仍 0 行), 分母口径会产生"46 表欠 stats"的误导性异常暗示

    每 schema 独立 try/except: 单库探测失败如实记入该 schema 的
    ``check`` 字段 (fail-loud), 不让监控自身成为新的静默源。
    """
    if mode not in ("quick", "full"):
        raise ValueError(f"invalid mode: {mode}")

    conn = get_connection()
    schemas: list[dict] = []
    for row in conn.execute("PRAGMA database_list").fetchall():
        schema, file_path = row[1], row[2]
        if schema == "temp":
            continue  # 会话级临时对象, 非持久索引载体
        entry: dict = {
            "schema": schema,
            "file": Path(file_path).name if file_path else "",
            "user_indexes": 0,
            "auto_indexes": 0,
            "tables_with_indexes": 0,
            "stat1_covered": 0,
            "check": "error",
            "check_errors": [],
            "check_ms": 0,
        }
        try:
            entry["user_indexes"] = conn.execute(
                f"SELECT COUNT(*) FROM \"{schema}\".sqlite_master "
                "WHERE type='index' AND name NOT LIKE 'sqlite_auto%'"
            ).fetchone()[0]
            entry["auto_indexes"] = conn.execute(
                f"SELECT COUNT(*) FROM \"{schema}\".sqlite_master "
                "WHERE type='index' AND name LIKE 'sqlite_auto%'"
            ).fetchone()[0]
            # planner 统计 (绝对数; 分母 tables_with_indexes 保留供数据侧,
            # 展示层不组成比率 — 小表/纯 autoindex 表 ANALYZE 有意跳过)
            entry["tables_with_indexes"] = conn.execute(
                f"SELECT COUNT(DISTINCT tbl_name) FROM \"{schema}\".sqlite_master "
                "WHERE type='index' AND tbl_name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
            try:
                entry["stat1_covered"] = conn.execute(
                    f"SELECT COUNT(DISTINCT tbl) FROM \"{schema}\".sqlite_stat1 "
                    f"WHERE tbl IN (SELECT DISTINCT tbl_name "
                    f"FROM \"{schema}\".sqlite_master "
                    "WHERE type='index' AND tbl_name NOT LIKE 'sqlite_%')"
                ).fetchone()[0]
            except sqlite3.Error:
                entry["stat1_covered"] = 0  # ANALYZE 从未跑过 → stat1 表不存在
            t0 = time.perf_counter()
            pragma = "integrity_check(100)" if mode == "full" else "quick_check"
            rows = conn.execute(f"PRAGMA \"{schema}\".{pragma}").fetchall()
            entry["check_ms"] = int((time.perf_counter() - t0) * 1000)
            msgs = [str(r[0]) for r in rows]
            if len(msgs) == 1 and msgs[0] == "ok":
                entry["check"] = "ok"
            else:
                entry["check"] = f"{len(msgs)} issues"
                entry["check_errors"] = msgs[:10]
        except Exception as e:
            entry["check"] = f"probe_failed: {type(e).__name__}: {e}"
        schemas.append(entry)

    return {
        "mode": mode,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "schemas": schemas,
        "totals": {
            "user_indexes": sum(s["user_indexes"] for s in schemas),
            "auto_indexes": sum(s["auto_indexes"] for s in schemas),
            "schemas_ok": sum(1 for s in schemas if s["check"] == "ok"),
            "schemas_total": len(schemas),
        },
    }

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
                log.info("archive_quality_logs: incremental_vacuum done")
            else:
                log.info("archive_quality_logs: auto_vacuum off, skip space reclaim")
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


def _qcl_retention_days() -> int:
    """qcl 保留窗口唯一事实源 = retention.json 台账 (缺声明兜底常量)。"""
    try:
        for s in load_telemetry_specs():
            if s.get("table") == "quality_check_logs":
                rd = s.get("retention_days")
                if isinstance(rd, int) and rd >= 1:
                    return rd
    except Exception as e:
        log.warning(f"_qcl_retention_days: ledger read failed: {e}")
    return DEFAULT_QUALITY_LOG_DAYS


def qcl_out_of_window_rows() -> int:
    """DEV-0324: 窗口外 qcl 残档数 — 真实清理执行后的不变量 = 0。

    cutoff 与 ``archive_quality_logs`` 完全同源 (Python UTC isoformat,
    台账 retention 天数)。清理报 ok=True 后本值 >0 = "名义成功实际空转"
    的直接证据 (DEV-0318 事故 53.8 万行积压正是此指纹, skip/failed 告警
    均不覆盖), 供 job 层 backlog 哨兵消费。
    """
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=_qcl_retention_days())).isoformat()
    return get_connection().execute(
        "SELECT COUNT(*) FROM quality_check_logs WHERE checked_at < ?",
        (cutoff,),
    ).fetchone()[0]


def quality_log_tiers(
    tier_days: int | None = None,
    tiers: int = DEFAULT_QUALITY_LOG_TIERS,
) -> dict:
    """DEV-0322 三档模型: quality_check_logs 按档宽分档统计行数与估算体积。

    口径与 ``archive_quality_logs`` 完全同源 (Python UTC isoformat cutoff,
    字符串前缀比较), 因此 ``bands`` 最后一档 (in_window=False) 的 rows
    **就是此刻点"清理"会归档掉的量** — 展示与执行不可能是两套数字。

    - tier_days 缺省读台账 (retention.json qcl retention_days / tiers)
    - 体积为估算: avg_row_bytes = (全表文本列 SUM(LENGTH) + 数值列按
      ~10B/行) / 总行数; 逐档 est_bytes = rows × avg_row_bytes
    """
    from datetime import datetime, timedelta, timezone

    conn = get_connection()
    retention = _qcl_retention_days()
    if tier_days is None:
        tier_days = max(1, retention // tiers)

    now = datetime.now(timezone.utc)
    qcl = "quality_check_logs"

    total_rows = conn.execute(f"SELECT COUNT(*) FROM {qcl}").fetchone()[0]
    text_bytes = conn.execute(
        f"SELECT COALESCE(SUM(LENGTH(COALESCE(item_id, '')) "
        f"+ LENGTH(COALESCE(gate_name, '')) + LENGTH(COALESCE(flags, '')) "
        f"+ LENGTH(COALESCE(reason, '')) + LENGTH(COALESCE(error_msg, '')) "
        f"+ LENGTH(COALESCE(checked_at, '')) + LENGTH(COALESCE(mode, ''))), 0) "
        f"FROM {qcl}"
    ).fetchone()[0]
    # id/passed/score_deduction 三个数值列粗估 10B/行 (est 口径, 文档化)
    avg_row_bytes = round((text_bytes + total_rows * 10) / total_rows) if total_rows else 0

    def _iso(dt):
        return dt.isoformat()

    bands: list[dict] = []
    for i in range(tiers):
        lo = _iso(now - timedelta(days=(i + 1) * tier_days))
        hi = _iso(now - timedelta(days=i * tier_days)) if i else None
        sql = f"SELECT COUNT(*) FROM {qcl} WHERE checked_at >= ?"
        args: list = [lo]
        if hi:
            sql += " AND checked_at < ?"
            args.append(hi)
        rows = conn.execute(sql, args).fetchone()[0]
        bands.append({
            "index": i + 1, "in_window": True,
            "from_days": (i + 1) * tier_days, "to_days": i * tier_days,
            "rows": rows, "est_bytes": rows * avg_row_bytes,
        })
    cutoff = _iso(now - timedelta(days=tier_days * tiers))
    out_rows = conn.execute(
        f"SELECT COUNT(*) FROM {qcl} WHERE checked_at < ?", (cutoff,)
    ).fetchone()[0]
    bands.append({
        "index": tiers + 1, "in_window": False,
        "from_days": None, "to_days": tier_days * tiers,
        "rows": out_rows, "est_bytes": out_rows * avg_row_bytes,
    })

    return {
        "tier_days": tier_days,
        "tiers": tiers,
        "window_days": tier_days * tiers,
        "ledger_retention_days": retention,
        "checked_at": now.isoformat(),
        "total_rows": total_rows,
        "avg_row_bytes": avg_row_bytes,
        "total_est_bytes": total_rows * avg_row_bytes,
        "bands": bands,
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
    ki = knowledge_items_table()
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
    ki = knowledge_items_table()
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
    ki = knowledge_items_table()
    ri = "raw_items"

    # quality_check_logs — DEV-0322: 口径从台账 retention 动态读取
    # (旧 SQL 硬编码 '-7 days' 且 datetime('now') 空格格式与 T 格式存储
    # 存在字符序偏差); 现在与 archive_quality_logs 同一 isoformat cutoff,
    # "可清理行"与"点清理真实归档量"恒等
    qcl_retention = _qcl_retention_days()
    qcl_cutoff = (datetime.now(timezone.utc)
                  - timedelta(days=qcl_retention)).isoformat()
    qcl_total = conn.execute(f"SELECT COUNT(*) FROM {qcl}").fetchone()[0]
    qcl_old = conn.execute(
        f"SELECT COUNT(*) FROM {qcl} WHERE checked_at < ?", (qcl_cutoff,)
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
            # DEV-0322: 口径 = 台账 retention (21d=3档), 与归档执行同源
            "older_than_retention": qcl_old,
            "retention_days": qcl_retention,
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
    "index_health",
    "load_telemetry_specs",
    "qcl_out_of_window_rows",
    "quality_log_tiers",
    "run_telemetry_window",
    "run_vacuum",
    "table_stats",
]
"""maintenance 域 scheduler job (v0.6 P0-③ 自 jobs.py 按域拆分)。
实现为搬运原文；跨域 job 调用经包命名空间动态解析以保住
patch("backend.scheduler.jobs.<fn>") 测试契约。
"""
import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import backend.scheduler.jobs as _jobs_pkg
from backend.logging_config import logger
from backend.repository.trend_repo import TrendRepository
from backend.scheduler.jobs._runtime import instrument_job, job_done_event

_logger = logger.bind(component="jobs")


async def map_rebuild_daily_job() -> None:
    """复利驱动器③: 每天 02:00 重建知识地图 (_MAP.md + graph.json)。"""
    try:
        from backend.services.map_updater import update_map

        result = await asyncio.to_thread(update_map)
        _logger.info(
            f"map_rebuild_daily: {result.get('total_items', 0)} items, "
            f"{result.get('total_concepts', 0)} concepts"
        )
    except Exception as e:
        _logger.error(f"map_rebuild_daily crashed: {e}")


def _trend_rebuild_hours(default: int = 168) -> int:
    """读 settings.trend.rebuild_hours, 缺失或脏值回落到 default。"""
    try:
        from backend.repository.db import get_connection

        row = get_connection().execute(
            "SELECT value FROM settings WHERE key = ?", ("trend.rebuild_hours",)
        ).fetchone()
        if row and row["value"] is not None:
            return max(1, int(row["value"]))
    except Exception as e:  # settings 缺表/脏值都不该让重建停摆
        _logger.debug(f"_trend_rebuild_hours: {e}")
    return default


async def trend_rebuild_job() -> None:
    """周期性重建 trend（不跑采集）

    窗口默认 168h（原硬编码 24h）。``/api/trends?hours=N`` 对超出快照窗口的桶
    一律补 0 —— 24h 快照下实测 168 点仅 19 个非零, "没有数据"被显示成
    "零资讯"; 判断层「时段吞吐」点阵正是按 168h 取数。
    """
    try:
        trend = TrendRepository()
        hours = _trend_rebuild_hours()
        # Phase 9 修复：trend.rebuild 是同步 sqlite3 操作，放 thread pool 避免阻塞 event loop
        count = await asyncio.to_thread(trend.rebuild, hours)
        _logger.info(f"trend_rebuild_job: {count} points ({hours}h window)")
    except Exception as e:
        _logger.error(f"trend_rebuild_job crashed: {e}")


async def source_reputation_rebuild_job() -> None:
    """Phase 3.5: 重算 source 信誉。"""
    try:
        from backend.quality.jobs import run_source_reputation_rebuild

        # Phase 9 修复：同步 DB 操作放 thread pool
        n = await asyncio.to_thread(run_source_reputation_rebuild)
        _logger.info(f"source_reputation_rebuild_job: {n} sources updated")
    except Exception as e:
        _logger.error(f"source_reputation_rebuild_job crashed: {e}")


async def export_rebuild_job() -> None:
    """Phase 4: 重建 export 缓存 HTML（每 30min 跑一次）。"""
    try:
        from backend.services.export_service import rebuild_export_cache

        # Phase 9 修复：同步 IO 放 thread pool
        etag = await asyncio.to_thread(rebuild_export_cache)
        _logger.info(f"export_rebuild_job: rebuilt etag={etag[:8]}...")
    except Exception as e:
        _logger.error(f"export_rebuild_job crashed: {e}")


@instrument_job("telemetry_window")
async def telemetry_window_job() -> None:
    """v0.5 SPEC §18: 7 天遥测窗口 — WARM 层遥测表滚动清理。

    按 retention.json 中 ``scheduled_in == "telemetry_window"`` 的声明
    执行: quality_check_logs 归档 (>7d, 吸收原 quality_logs_cleanup_job)、
    crawler_runs / raw_items truncate。台账是唯一事实源 — 新增遥测表
    只需在 retention.json 打标签, 无需改本 job。

    每周日 05:00 Asia/Shanghai 注册 (与原 quality_logs_cleanup 同时段,
    避免与 04:00 soul / 04:30 backup / 周日链冲突)。
    """
    from backend.services.maintenance_service import run_telemetry_window

    result = await asyncio.to_thread(run_telemetry_window, False)
    if result.get("failed"):
        raise RuntimeError(
            f"telemetry window partial failure: "
            f"{[r.get('table') for r in result['results'] if not r.get('ok')]}"
        )
    _logger.info(
        f"telemetry_window_job: tables={result['tables']} "
        f"deleted={result['rows_deleted']} archived={result['rows_archived']}"
    )


@instrument_job("db_diet")
async def db_diet_job() -> None:
    """v0.5 M2-Task4: weekly_maintenance 链末尾调 db_diet。

    调用 ``scripts/db_diet.py`` 作为子进程 (避免把 cleanup_table 逻辑
    复制进 services 层造成双份维护), dry_run 模式默认开, 失败只 log.error。

    v0.5 M2-Task5: 包了 @instrument_job 装饰器, 完成后自动推 job_done SSE。
    """
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "db_diet.py"
    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    try:
        # ASYNC221 根治: 子进程最长可阻塞 60s, to_thread 丢线程池避免卡死调度器事件循环
        proc = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(script), "--dry-run", "--json"],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        _logger.info(
            f"db_diet_job (dry-run): rc={proc.returncode} "
            f"stdout_lines={len(proc.stdout.splitlines())}"
        )
    except Exception as e:
        _logger.error(f"db_diet_job crashed: {e}")
        raise  # 让 instrument_job 捕获并记 ok=False


async def weekly_maintenance_job() -> None:
    """v1.8 R3: 周日维护链 — SOUL 重生成 → 掌握度迁移 → 周回顾 → db_diet。

    原 soul_weekly (Sun 04:00) / migrate_weekly (Sun 05:00) /
    summary_weekly (Sun 06:00) 三个 cron job 合并为单 job 顺序执行,
    保持原链式语义 (每个子 job 自带异常隔离, 不会中断后续)。

    v0.5 M2-Task4: 末尾追加 db_diet_job — 按 retention.json 台账清表,
    DB 瘦身的统一入口 (替代人工跑 scripts/db_diet.py)。
    """
    await _jobs_pkg.scheduled_soul_job()
    await _jobs_pkg.scheduled_migrate_job()
    await _jobs_pkg.scheduled_summary_job()
    await db_diet_job()
    # v0.5: 周日轮转 — 强制 full backup, 重置增量链
    await _force_full_backup_rotate()


async def _force_full_backup_rotate() -> None:
    """周日 weekly 强制 full backup (重置增量链)。

    与 daily_db_backup_job (增量) 互补, 保证周一到周日: 6 增量 + 1 full。
    """
    try:
        from backend.services.backup_service import backup_incremental

        result = await asyncio.to_thread(backup_incremental, True)  # force_full=True
        if result.get("mode") == "full":
            _logger.info(
                f"weekly_full_rotate: full={result['path'].rsplit('/', 1)[-1]} "
                f"({result['size'] / 1e6:.1f} MB)"
            )
    except Exception as e:
        _logger.error(f"weekly_full_rotate crashed: {e}")


@instrument_job("db_backup_daily")
async def daily_db_backup_job() -> None:
    """P1: 每日 04:30 (Asia/Shanghai) 数据库自动备份。

    v0.5: 改走增量备份 (backup_incremental), 链累积超 MAX_INCREMENTAL_PAGES
    或周日 weekly_maintenance 强制轮转时自动升级为 full。

    失败只 log.error (不抛), 保证 scheduler 不死循环。
    """
    try:
        from backend.services.backup_service import backup_incremental

        result = await asyncio.to_thread(backup_incremental)
        if result.get("mode") == "full":
            _logger.info(
                f"daily_db_backup_job (full): {result['path'].rsplit('/', 1)[-1]} "
                f"({result['size'] / 1e6:.1f} MB) retained={result['retained']} "
                f"removed={result['removed']}"
            )
        else:
            _logger.info(
                f"daily_db_backup_job (incremental): "
                f"{result.get('pages', 0)} pages, {result.get('size', 0)} bytes, "
                f"kept={result.get('incremental_kept', 0)} removed={result.get('incremental_removed', 0)}"
            )
    except Exception as e:
        _logger.error(f"daily_db_backup_job crashed: {e}")
        raise  # 让 instrument_job 标记 ok=False


async def fts_rebuild_job() -> None:
    """v1.7 Phase 5: FTS5 索引重建 (5min).

    unified_fts 是迁移 033 创建的虚拟表, 此 job 触发其 REBUILD 优化查询性能.
    """
    try:
        from backend.repository.db import get_connection

        def _rebuild():
            conn = get_connection()
            conn.execute("INSERT INTO unified_fts(unified_fts) VALUES('rebuild')")

        await asyncio.to_thread(_rebuild)
    except Exception as e:
        # 表可能不存在 (旧 DB), 不报严重错
        _logger.debug(f"fts_rebuild_job: {e}")


async def wiki_items_fts_sync_job() -> None:
    """v0.6 Phase 6: wiki_items_fts 失同步自愈 (与 fts_rebuild_job 链式触发).

    正常路径: 073_v0.6_wiki_items_fts_sync.sql 的 3 触发器 (AI/AD/AU)
    自动维护 wiki_items_fts 与 knowledge_items 同步. 本 job 是兜底:
    触发器被误删 / 大批量历史数据迁移后, 比较两侧 COUNT, 失同步则
    ``INSERT INTO wiki_items_fts(wiki_items_fts) VALUES('rebuild')``
    (FTS5 的增量 rebuild 自愈命令).
    """
    try:
        from backend.repository.db import get_connection

        def _sync():
            conn = get_connection()
            cur = conn.execute(
                "SELECT (SELECT COUNT(*) FROM warm.knowledge_items),"
                " (SELECT COUNT(*) FROM wiki_items_fts)"
            )
            src_count, fts_count = cur.fetchone()
            if src_count != fts_count:
                _logger.warning(
                    f"wiki_items_fts_sync_job: drift detected "
                    f"(knowledge_items={src_count}, wiki_items_fts={fts_count}); "
                    "rebuilding"
                )
                # FTS5 没有 DELETE FROM 语法; 用 'delete-all' 命令清空 (SQLite
                # 3.7.4+, 对 content='/external 表都支持; content='' 表更稳)。
                # 'delete-all' 会清除全部 rowid 数据但保留表结构, 之后可重新
                # INSERT 填充。
                conn.execute(
                    "INSERT INTO wiki_items_fts(wiki_items_fts) VALUES('delete-all')"
                )
                conn.execute(
                    """
                    INSERT INTO wiki_items_fts(rowid, id, title, topic, tags, type)
                    SELECT rowid, id, IFNULL(title, ''), IFNULL(topic, ''),
                           IFNULL(tags, ''), IFNULL(type, '')
                    FROM warm.knowledge_items
                    """
                )
                conn.execute(
                    "INSERT INTO wiki_items_fts(wiki_items_fts) VALUES('optimize')"
                )

        await asyncio.to_thread(_sync)
    except Exception as e:
        # 表可能不存在 (旧 DB, 073 未跑), 不报严重错
        _logger.debug(f"wiki_items_fts_sync_job: {e}")


async def profile_decay_job() -> None:
    """v1.7 Phase 5: 每日 03:00 Shanghai 衰减所有 profile 权重."""
    try:
        from backend.services.profile_service import decay_all
        n = await asyncio.to_thread(decay_all)
        _logger.info(f"profile_decay_job: decayed {n} entries")
    except Exception as e:
        _logger.error(f"profile_decay_job crashed: {e}")


async def retention_decay_job() -> None:
    """周 job: 扫 ``llm-wiki-2.0/retention.json``, 按 Ebbinghaus 公式更新 current_score。

    关闭策略: ``config.llm_wiki_v2=False`` 时直接跳过。
    """
    from backend.config import config

    if not config.llm_wiki_v2:
        _logger.info("retention_decay_job skipped (llm_wiki_v2 disabled)")
        return

    from backend.services.retention_engine import run_decay

    _t0 = datetime.now(tz=timezone.utc)
    retention_path = config.llm_wiki_v2_path / "retention.json"
    try:
        stats = run_decay(retention_path)
        _logger.info(
            f"retention_decay_job: {stats} (path={retention_path})"
        )
    except Exception as e:
        _logger.error(f"retention_decay_job crashed: {e}")
        try:
            job_done_event("retention_decay", "retention_decay", 0, ok=False)
        except Exception:
            pass
        return
    duration_ms = int((datetime.now(tz=timezone.utc) - _t0).total_seconds() * 1000)
    ok = stats.get("errors", 0) == 0
    try:
        job_done_event("retention_decay", "retention_decay", duration_ms, ok=ok)
    except Exception:
        pass


async def attention_aggregate_job() -> None:
    """Phase 17: 每 30 分钟聚合 attention 事件并更新 attention_score。

    调用 attention_scorer.batch_score() 批量计算。
    清理 30 天前的过期 attention_events。
    """
    try:
        from backend.services.attention_scorer import batch_score

        result = await asyncio.to_thread(batch_score)
        _logger.info(f"attention_aggregate_job: updated={result.get('updated')}, errors={result.get('errors')}")

        # 清理 30 天前的过期事件
        from datetime import datetime, timedelta, timezone

        from backend.repository.db import get_connection

        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        conn = get_connection()
        conn.execute("DELETE FROM attention_events WHERE created_at < ?", (cutoff,))
        deleted = conn.total_changes
        _logger.info(f"attention_aggregate_job: cleaned {deleted} expired events")
    except Exception as e:
        _logger.error(f"attention_aggregate_job crashed: {e}")


async def bid_expiry_check_job() -> None:
    """Phase 1.4: 每 30 分钟检查过期标讯并标记。

    查询 bid_details 中 deadline < now() 且尚未标记的条目，
    更新 bid_status = '已过期'。
    失败只 log.warning，不抛异常。
    """
    try:
        from backend.repository.bid_detail_repo import BidDetailRepo

        repo = BidDetailRepo()
        expired = await asyncio.to_thread(repo.get_expired)
        if not expired:
            return

        marked = 0
        for row in expired:
            try:
                ok = await asyncio.to_thread(repo.mark_expired, row["item_id"])
                if ok:
                    marked += 1
            except Exception:
                continue

        _logger.info(
            f"bid_expiry_check_job: found {len(expired)} expired, marked {marked}"
        )
    except Exception as e:
        _logger.warning(f"bid_expiry_check_job: {e}")


async def planning_action_check_job() -> None:
    """Phase 13: 每 600s 生成规划动作."""
    from backend.services.planning_service import PlanningService
    try:
        service = PlanningService()
        report = await asyncio.to_thread(service.generate_actions)
        logger.info(
            "planning_action_check_job: "
            + " ".join(f"{k}={v}" for k, v in report.items())
        )
    except Exception as e:
        logger.error(f"planning_action_check_job crashed: {e}")


async def scheduled_stats_job() -> None:
    """Phase 1f Task 6.9: 定时回收已发布文章统计数据。

    每日 06:00 (Asia/Shanghai) 触发。
    失败只 log.error，不抛异常。
    """
    try:
        from backend.services.stats_recycle_service import recycle_stats

        result = await asyncio.to_thread(recycle_stats)
        _logger.info(
            f"scheduled_stats_job: recycled={result.get('recycled')}, "
            f"skipped={result.get('skipped')}"
        )
    except Exception as e:
        _logger.error(f"scheduled_stats_job crashed: {e}")


@instrument_job("observability_ttl")
async def observability_ttl_job() -> None:
    """v0.7 Batch 1: 观测表 TTL 清理 — 按迁移 080 的 retention 注释执行。

    job_runs 30d / agent_runs 30d / process_events 14d / audit_log 90d。
    llm_usage_log 由 retention.json `scheduled_in == "telemetry_window"` 路径
    维护 (沿用现有周日凌晨清理链); 本 job 不重复清理。

    每小时一次: 4 张表均为追加写入, 缓慢累积, 高频清理能把单次 DELETE
    控制在毫秒级; 同时错峰 telemetry_window (周日凌晨) 的批量清理。
    """
    try:
        from datetime import datetime, timedelta, timezone

        from backend.repository.db import get_connection

        now = datetime.now(timezone.utc)
        ttl_table = {
            "job_runs": now - timedelta(days=30),
            "agent_runs": now - timedelta(days=30),
            "process_events": now - timedelta(days=14),
            "audit_log": now - timedelta(days=90),
        }
        ts_column = {
            "job_runs": "started_at",
            "agent_runs": "started_at",
            "process_events": "occurred_at",
            "audit_log": "occurred_at",
        }
        deleted_total = 0
        per_table = {}
        for table, cutoff in ttl_table.items():
            col = ts_column[table]
            cur = get_connection().execute(
                f"DELETE FROM {table} WHERE {col} < ?", (cutoff.isoformat(),)
            )
            n = cur.rowcount
            per_table[table] = n
            deleted_total += n
        _logger.info(
            f"observability_ttl_job: deleted={deleted_total} per_table={per_table}"
        )
    except Exception as e:
        _logger.error(f"observability_ttl_job crashed: {e}")
        raise  # 让 instrument_job 落 ok=False

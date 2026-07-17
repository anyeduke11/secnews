"""APScheduler 调度的 job 函数

These are thin async functions invoked by
:class:`backend.scheduler.scheduler.HotspotScheduler`. They delegate the
real work to :class:`backend.services.collection_service.CollectionService`
and :class:`backend.repository.trend_repo.TrendRepository` — the
scheduler itself is just a timing layer.

The ``CollectionService`` instance is injected at scheduler start time
via :func:`set_service`; this avoids a module-level import cycle between
``backend.scheduler`` and ``backend.services``.
"""
import asyncio

from backend.logging_config import logger
from backend.repository.trend_repo import TrendRepository

# 全局 service 实例（由 scheduler.py 注入）
_service = None
_logger = logger.bind(component="jobs")


def set_service(service) -> None:
    """scheduler.py 在 start() 前注入"""
    global _service
    _service = service


def reset_service() -> None:
    global _service
    _service = None


async def collect_all_job() -> None:
    """周期性执行完整采集 + trend rebuild"""
    if _service is None:
        _logger.error("service not initialized, skipping collect_all_job")
        return
    try:
        report = await _service.run_once()
        _logger.info(
            f"collect_all_job: total={report.total}, "
            f"success={report.success_count}, failed={report.failed_count}, "
            f"duration={report.duration_ms}ms"
        )
    except Exception as e:
        _logger.error(f"collect_all_job crashed: {e}")


async def trend_rebuild_job() -> None:
    """周期性重建 trend（不跑采集）"""
    try:
        trend = TrendRepository()
        # Phase 9 修复：trend.rebuild 是同步 sqlite3 操作，放 thread pool 避免阻塞 event loop
        count = await asyncio.to_thread(trend.rebuild, 24)
        _logger.info(f"trend_rebuild_job: {count} points")
    except Exception as e:
        _logger.error(f"trend_rebuild_job crashed: {e}")


async def url_content_check_job() -> None:
    """Phase 3.5: 抽样跑 URLContent gate。"""
    try:
        from backend.quality.jobs import run_url_content_check

        result = await run_url_content_check()
        _logger.info(
            f"url_content_check_job: {result}"
        )
    except Exception as e:
        _logger.error(f"url_content_check_job crashed: {e}")


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


async def daily_snapshot_job() -> None:
    """v1.3.0 Phase 4: 日级趋势快照（每天 00:30 UTC）。"""
    try:
        from backend.services.weekly_report_service import WeeklyReportService

        svc = WeeklyReportService()
        count = await asyncio.to_thread(svc.take_daily_snapshot)
        _logger.info(f"daily_snapshot_job: {count} categories snapshotted")
    except Exception as e:
        _logger.error(f"daily_snapshot_job crashed: {e}")


async def weekly_report_job() -> None:
    """v1.3.0 Phase 4: 周报自动生成（每周一 02:00 UTC）。"""
    try:
        from backend.services.weekly_report_service import WeeklyReportService

        svc = WeeklyReportService()
        report = await asyncio.to_thread(svc.generate_report)
        _logger.info(f"weekly_report_job: generated for {report.get('week_start', '?')}")
    except Exception as e:
        _logger.error(f"weekly_report_job crashed: {e}")


async def scheduled_compile_job() -> None:
    """Phase 1d: 定时编译任务 — 检测 stale items 并创建编译任务。

    每日 02:00 (Asia/Shanghai) + 每周日 03:00 (Asia/Shanghai) 触发。
    失败只 log.error，不抛异常。
    """
    try:
        from backend.services.compiler import detect_stale_items, create_compile_task

        result = await asyncio.to_thread(detect_stale_items)
        stale_items = result.get("stale_items", [])
        if stale_items:
            compile_result = await asyncio.to_thread(create_compile_task, stale_items)
            _logger.info(
                f"scheduled_compile_job: created task {compile_result.get('task_id')} "
                f"for {len(stale_items)} stale items"
            )
        else:
            _logger.info("scheduled_compile_job: no stale items")
    except Exception as e:
        _logger.error(f"scheduled_compile_job crashed: {e}")


async def scheduled_soul_job() -> None:
    """Phase 1f Task 6.8: 定时检查 SOUL.md 周期（>7天未更新则触发重新生成）。

    每周日 04:00 (Asia/Shanghai) 触发。
    失败只 log.error，不抛异常。
    """
    try:
        from datetime import datetime, timezone, timedelta

        def _read_soul_updated_at():
            from backend.services.knowledge_sync import parse_frontmatter
            from backend.services.soul_service import SOUL_PATH

            if not SOUL_PATH.exists():
                return None
            fm = parse_frontmatter(SOUL_PATH)
            if fm is None:
                return None
            updated_at_str = fm.get("updated_at")
            if not updated_at_str:
                return None
            try:
                updated_at = datetime.fromisoformat(str(updated_at_str))
            except (ValueError, TypeError):
                return None
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            return updated_at

        updated_at = await asyncio.to_thread(_read_soul_updated_at)
        now = datetime.now(timezone.utc)

        if updated_at is None or (now - updated_at) > timedelta(days=7):
            from backend.services.soul_service import create_soul_task

            result = await asyncio.to_thread(create_soul_task)
            _logger.info(
                f"scheduled_soul_job: created soul task {result.get('task_id')}"
            )
        else:
            age_days = (now - updated_at).days
            _logger.info(
                f"scheduled_soul_job: SOUL.md fresh ({age_days} days), skipping"
            )
    except Exception as e:
        _logger.error(f"scheduled_soul_job crashed: {e}")


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


async def scheduled_migrate_job() -> None:
    """Phase 1f Task 6.10: 定时迁移高掌握度条目到本地 wiki。

    每周日 05:00 (Asia/Shanghai) 触发。
    失败只 log.error，不抛异常。
    """
    try:
        from backend.services.federation_service import migrate_high_mastery_items

        result = await asyncio.to_thread(migrate_high_mastery_items)
        _logger.info(
            f"scheduled_migrate_job: migrated={result.get('migrated')}, "
            f"skipped={result.get('skipped')}"
        )
    except Exception as e:
        _logger.error(f"scheduled_migrate_job crashed: {e}")


# ---------------------------------------------------------------------------
# Phase 42: 跨端配置同步 (Q2 决策: 每周一 10:30 + 启动 catch-up)
# ---------------------------------------------------------------------------
async def sync_job(*, force: bool = False) -> None:
    """周期性同步 (scheduler 触发); 手动触发可用 force=True 跳过 unlock 检查。

    跳过条件
    --------
    - master_key 未 unlock (即用户在 30 分钟内没输过密码) → 跳过, 写一条
      ``status=skipped`` 的 history 让用户能在 UI 里看到为什么没同步
    - sync_configs.auto_sync_enabled = 0 → 跳过
    - WebDAV 未配置 → 跳过

    force=True 用于:
    - 启动 catch-up (scheduler 启动时若 "本应已同步但未同步", 强制触发)
    - 手动 push/pull 的 catch-up 检测
    """
    from datetime import datetime, timezone
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    from backend.repository.sync_configs_repo import SyncConfigRepository
    from backend.services.secrets_service import _is_unlocked
    from backend.services.sync_service import SyncService

    cfg_repo = SyncConfigRepository()
    cfg = cfg_repo.get_default()
    if cfg is None or not cfg.webdav_url or not cfg.webdav_username:
        _logger.info("sync_job: WebDAV 未配置, 跳过")
        return
    if not cfg.auto_sync_enabled and not force:
        _logger.info("sync_job: auto_sync_enabled=False, 跳过")
        return

    # master_key unlock 检查 (非 force 模式)
    if not force:
        ek = EncryptionKeyRepository().get_default()
        if ek is None or not _is_unlocked(ek.id):
            _logger.warning("sync_job: master_key 未解锁, 跳过同步")
            from backend.repository.sync_history_repo import SyncHistoryRepository
            SyncHistoryRepository().write(
                config_id=cfg.id,
                direction="bidirectional",
                status="error",
                error_message="master_key 未解锁, 自动同步已跳过",
                started_at=datetime.now(timezone.utc).isoformat(),
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            return

    # 触发同步 (用 secrets_service 里的 fernet_key 派生 master_key 不行,
    # sync_service 需要原始 master_key 字符串; 但我们的 unlock state 只存
    # fernet_key, 没有 master_key。简化方案: 只在 force=True 路径下走
    # bidirectional; 自动模式下若 _is_unlocked 则调用一个独立 helper
    # (auto_sync_with_unlocked_key) — 但 secret api_key 加密用的是
    # master_key 派生 key, unlock 后我们有 fernet_key 即可解密 webdav_pwd。
    try:
        from backend.services.secrets_service import _unlock_state
        ek = EncryptionKeyRepository().get_default()
        if ek is None or not _is_unlocked(ek.id):
            _logger.warning("sync_job: master_key 突然过期, 跳过")
            return
        fernet_key = _unlock_state[ek.id]["fernet_key"]
        svc = SyncService()
        result = await svc.bidirectional_with_fernet_key(fernet_key)
        _logger.info(f"sync_job: {result}")
    except Exception as e:
        _logger.error(f"sync_job crashed: {e}")


def should_run_catchup(last_sync_at: str | None, now: datetime) -> bool:
    """判断启动时是否需要补上同步 (Q2 决策)。

    规则
    ----
    - ``now`` 是 Asia/Shanghai 本地时间
    - 今天是周一 且 ``now.hour*60+now.minute >= 10*60+30`` (10:30 之后)
    - last_sync_at 为 None (从未同步) → catch-up
    - last_sync_at 在本周一 00:00 之前 → catch-up
    - 否则 (本周一 10:30 后已同步) → 不需要 catch-up, 等下周一 10:30
    """
    import datetime as _dt
    if now.weekday() != 0:  # 0 = Monday
        return False
    cutoff_min = now.hour * 60 + now.minute
    if cutoff_min < 10 * 60 + 30:
        return False
    monday_start = _dt.datetime(now.year, now.month, now.day,
                                tzinfo=now.tzinfo)
    if last_sync_at is None:
        return True
    try:
        last = _dt.datetime.fromisoformat(last_sync_at)
        if last.tzinfo is None:
            last = last.replace(tzinfo=_dt.timezone.utc)
        # 转为 Asia/Shanghai
        last_sh = last.astimezone(now.tzinfo)
        return last_sh < monday_start
    except Exception:
        return True


async def scheduled_summary_job() -> None:
    """Phase 1j Task 10.8: 每周日 06:00 (Asia/Shanghai) 生成本周知识回顾。

    链式触发于 SOUL cron (Sun 04:00) + migrate cron (Sun 05:00) 之后。
    失败只 log.error，不抛异常。
    """
    try:
        from backend.services.summary_service import generate_weekly_summary

        result = await asyncio.to_thread(generate_weekly_summary, None)
        _logger.info(
            f"scheduled_summary_job: generated {result.get('year_week')} "
            f"(items={result.get('items_count')}, concepts={result.get('concepts_count')})"
        )
    except Exception as e:
        _logger.error(f"scheduled_summary_job crashed: {e}")


__all__ = [
    "set_service",
    "reset_service",
    "collect_all_job",
    "trend_rebuild_job",
    "url_content_check_job",
    "source_reputation_rebuild_job",
    "export_rebuild_job",
    "sync_job",
    "should_run_catchup",
    "daily_snapshot_job",
    "weekly_report_job",
    "scheduled_compile_job",
    "scheduled_soul_job",
    "scheduled_stats_job",
    "scheduled_migrate_job",
    "scheduled_summary_job",
]

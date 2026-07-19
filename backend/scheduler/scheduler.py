"""APScheduler 封装

:class:`HotspotScheduler` is the lifecycle owner for the periodic
collection jobs. It uses ``apscheduler.schedulers.asyncio.AsyncIOScheduler``
so the registered job functions can be plain ``async def`` coroutines.

Lifecycle
---------
1. ``attach_service(service)`` — inject the ``CollectionService``
   instance. Must be called before ``start()``; ``jobs.set_service``
   is called as a side-effect so the job functions can find it.
2. ``start()`` — start APScheduler, register the periodic jobs, and
   schedule a one-shot initial run after a 5s warm-up delay.
3. ``stop()`` — graceful shutdown (waits for in-flight jobs to finish).
4. ``reschedule(interval_seconds)`` — dynamically adjust the
   ``collect_all`` interval at runtime (e.g. driven by the settings UI).

Both jobs (``collect_all`` and ``trend_rebuild``) run on the same
interval (``config.collect_interval_seconds``, default 300s) — the
trend rebuild is idempotent so a coarser schedule is unnecessary.

Phase 24 bug fix
----------------
之前 `next_run_time=None` 显式设为 None 的 jobs (collect_all, url_content_check,
source_reputation_rebuild, export_rebuild) 在 IntervalTrigger 下首次跑完后
next_run_time 永久为 None, **永远不再调度**。trend_rebuild 没设 None 所以正常。
现在统一用 start_date 替代 next_run_time=None, 确保 trigger 自动从当前时间计算。
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from backend.config import config
from backend.logging_config import logger
from backend.scheduler import jobs

_logger = logger.bind(component="scheduler")

# Phase 42: 跨端同步的固定时区 (用户决策 Q2: 每周一 10:30 Asia/Shanghai)
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


# Module-level singleton (used by /api/health for status reads)
_scheduler_instance: Optional["HotspotScheduler"] = None


def get_scheduler() -> Optional["HotspotScheduler"]:
    """Return the module-level scheduler singleton (or None if not yet started)."""
    return _scheduler_instance


def set_scheduler(scheduler: "HotspotScheduler") -> None:
    _scheduler_instance = scheduler


class HotspotScheduler:
    """APScheduler 调度器封装"""

    def __init__(self, service=None, interval: int | None = None):
        self.service = service
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._interval = (
            interval if interval is not None
            else config.collect_interval_seconds
        )
        self.logger = logger.bind(component="scheduler")

    def attach_service(self, service) -> None:
        """注入 CollectionService（start() 之前调用）"""
        self.service = service
        jobs.set_service(service)

    def start(self) -> None:
        """启动调度器 + 立即触发 collect_all"""
        if self.scheduler is not None:
            self.logger.warning("scheduler already started")
            return

        if self.service is None:
            raise RuntimeError("service not attached; call attach_service() first")

        self.scheduler = AsyncIOScheduler(timezone="UTC")
        # Phase 24: 用 start_date 替代 next_run_time=None。apscheduler 在
        # `next_run_time=None` + `IntervalTrigger` 组合下,首次跑完后 next_run_time
        # 不会被 trigger 自动更新成下一次,导致永久不再调度。
        # `start_date=now` 让 trigger 从当前时间计算 next_run_time, 自动链式调度。
        _now_utc = datetime.now(tz=timezone.utc)
        # job 1: 完整采集
        self.scheduler.add_job(
            jobs.collect_all_job,
            trigger=IntervalTrigger(seconds=self._interval, start_date=_now_utc),
            id="collect_all",
            name="collect all hotspots",
            replace_existing=True,
            # 首次跑由 _run_initial 在 5s 后触发;trigger 自身也从 start_date 开始
        )
        # job 2: 趋势重建（与采集同步；每 300 秒）
        self.scheduler.add_job(
            jobs.trend_rebuild_job,
            trigger=IntervalTrigger(seconds=self._interval, start_date=_now_utc),
            id="trend_rebuild",
            name="rebuild trend snapshots",
            replace_existing=True,
        )
        # Phase 3.5: job 3 — URL 内容验证（默认 5min）
        self.scheduler.add_job(
            jobs.url_content_check_job,
            trigger=IntervalTrigger(seconds=300, start_date=_now_utc),
            id="url_content_check",
            name="async url content quality check",
            replace_existing=True,
        )
        # Phase 3.5: job 4 — 来源信誉重算（默认 6h）
        self.scheduler.add_job(
            jobs.source_reputation_rebuild_job,
            trigger=IntervalTrigger(seconds=21600, start_date=_now_utc),
            id="source_reputation_rebuild",
            name="source reputation rebuild",
            replace_existing=True,
        )
        # Phase 4: job 5 — 导出预生成（每 30min）
        self.scheduler.add_job(
            jobs.export_rebuild_job,
            trigger=IntervalTrigger(seconds=1800, start_date=_now_utc),
            id="export_rebuild",
            name="export cache rebuild",
            replace_existing=True,
        )
        # Phase 42: job 6 — 跨端配置同步 (Q2 决策: 每周一 10:30 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.sync_job,
            trigger=CronTrigger(
                day_of_week="mon", hour=10, minute=30,
                timezone=SHANGHAI_TZ,
            ),
            id="sync",
            name="cross-device config sync (Mon 10:30)",
            replace_existing=True,
        )
        # v1.3.0 Phase 4: job 7 — 日级趋势快照 (每天 00:30 UTC)
        self.scheduler.add_job(
            jobs.daily_snapshot_job,
            trigger=CronTrigger(hour=0, minute=30, timezone="UTC"),
            id="daily_snapshot",
            name="daily trend snapshot (00:30 UTC)",
            replace_existing=True,
        )
        # v1.3.0 Phase 4: job 8 — 周报自动生成 (每周一 02:00 UTC)
        self.scheduler.add_job(
            jobs.weekly_report_job,
            trigger=CronTrigger(day_of_week="mon", hour=2, minute=0, timezone="UTC"),
            id="weekly_report",
            name="weekly report generation (Mon 02:00 UTC)",
            replace_existing=True,
        )
        # Phase 1d: job 9 — 定时编译 (每日 02:00 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.scheduled_compile_job,
            trigger=CronTrigger(hour=2, timezone=SHANGHAI_TZ),
            id="compile_daily",
            name="knowledge compile (daily 02:00)",
            replace_existing=True,
        )
        # Phase 1d: job 10 — 定时编译 (每周日 03:00 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.scheduled_compile_job,
            trigger=CronTrigger(day_of_week="sun", hour=3, timezone=SHANGHAI_TZ),
            id="compile_weekly",
            name="knowledge compile (Sun 03:00)",
            replace_existing=True,
        )
        # Phase 1f Task 6.8: job 11 — SOUL.md 周期更新 (每周日 04:00 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.scheduled_soul_job,
            trigger=CronTrigger(day_of_week="sun", hour=4, timezone=SHANGHAI_TZ),
            id="soul_weekly",
            name="soul regenerate (Sun 04:00)",
            replace_existing=True,
        )
        # Phase 1f Task 6.9: job 12 — 发布后数据回收 (每日 06:00 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.scheduled_stats_job,
            trigger=CronTrigger(hour=6, timezone=SHANGHAI_TZ),
            id="stats_daily",
            name="stats recycle (daily 06:00)",
            replace_existing=True,
        )
        # Phase 1f Task 6.10: job 13 — 掌握度迁移 (每周日 05:00 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.scheduled_migrate_job,
            trigger=CronTrigger(day_of_week="sun", hour=5, timezone=SHANGHAI_TZ),
            id="migrate_weekly",
            name="mastery migration (Sun 05:00)",
            replace_existing=True,
        )
        # Phase 1j Task 10.8: job 14 — 周回顾生成 (每周日 06:00 Asia/Shanghai)
        # 链式触发：SOUL(04:00) → migrate(05:00) → summary(06:00)
        self.scheduler.add_job(
            jobs.scheduled_summary_job,
            trigger=CronTrigger(day_of_week="sun", hour=6, timezone=SHANGHAI_TZ),
            id="summary_weekly",
            name="weekly summary (Sun 06:00)",
            replace_existing=True,
        )
        # Phase 2a CodeGarden: job 15 — 上游同步 (每日 09:00 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.cg_upstream_sync_job,
            trigger=CronTrigger(hour=9, timezone=SHANGHAI_TZ),
            id="cg_upstream_sync",
            name="codegarden upstream sync (daily 09:00)",
            replace_existing=True,
        )
        self.scheduler.start()
        self.logger.info(
            f"scheduler started, jobs: collect_all (every {self._interval}s), "
            f"trend_rebuild (every {self._interval}s), "
            f"url_content_check, source_reputation_rebuild"
        )
        # 注册到模块级 singleton
        set_scheduler(self)
        # 启动后立即异步触发一次 collect_all
        asyncio.get_event_loop().create_task(self._run_initial())

    async def _run_initial(self) -> None:
        """启动后延迟 5s 执行首次采集 + 跨端同步 catch-up 检查"""
        await asyncio.sleep(5)
        await jobs.collect_all_job()
        # Phase 42: 启动 catch-up (Q2 决策)
        try:
            from backend.repository.sync_configs_repo import SyncConfigRepository
            from backend.scheduler.jobs import should_run_catchup
            cfg = SyncConfigRepository().get_default()
            if cfg is not None and cfg.auto_sync_enabled:
                now_sh = datetime.now(tz=SHANGHAI_TZ)
                if should_run_catchup(cfg.last_sync_at, now_sh):
                    self.logger.info(
                        f"sync catch-up: 本周一 10:30 后未同步 (last_sync_at={cfg.last_sync_at})"
                    )
                    await jobs.sync_job(force=True)
                else:
                    self.logger.info(
                        f"sync catch-up: 无需 (last_sync_at={cfg.last_sync_at}, now={now_sh.isoformat()})"
                    )
        except Exception as e:
            self.logger.warning(f"sync catch-up check failed (ignored): {e}")

    def stop(self, wait: bool = True, timeout: float = 60.0) -> None:
        """优雅关闭调度器（Phase 8 容错版：所有异常内部吞掉，returncode=0）"""
        try:
            if self.scheduler is None:
                return
            self.logger.info("scheduler stopping...")
            try:
                self.scheduler.shutdown(wait=wait)
            except Exception as e:
                self.logger.warning(f"scheduler.shutdown error (ignored): {e}")
            self.scheduler = None
            try:
                jobs.reset_service()
            except Exception as e:
                self.logger.warning(f"jobs.reset_service error (ignored): {e}")
            self.logger.info("scheduler stopped")
        except Exception as e:
            # Phase 8: 任何未捕获异常都吞掉，确保 SIGTERM rc=0
            self.logger.warning(f"stop() outer error (ignored): {e}")

    def reschedule(self, interval_seconds: int) -> None:
        """动态调整 collect_all 间隔"""
        if self.scheduler is None:
            self._interval = interval_seconds
            return
        self.scheduler.reschedule_job(
            "collect_all",
            trigger=IntervalTrigger(seconds=interval_seconds, start_date=datetime.now(tz=timezone.utc)),
        )
        self._interval = interval_seconds
        self.logger.info(f"rescheduled collect_all to {interval_seconds}s")


__all__ = ["HotspotScheduler"]

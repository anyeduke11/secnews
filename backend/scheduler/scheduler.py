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

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.config import config
from backend.extensions import is_extension_enabled
from backend.logging_config import logger
from backend.scheduler import jobs

_logger = logger.bind(component="scheduler")

# Phase 42: 跨端同步的固定时区 (用户决策 Q2: 每周一 10:30 Asia/Shanghai)
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# P0.5: 调度器并发限制
# AsyncIOExecutor 是单线程异步执行器, 本身就限制并发 (同时只有一个协程运行)。
# max_instances=1: 同一 job 不重叠 (collect_all 跑 5min 时, 下一轮不启动)
# coalesce=True: 错过的合并为一次 (服务重启后不补跑堆积的 job)
# 这两个配置组合防止 43 个 job 资源耗尽。


def create_scheduler() -> AsyncIOScheduler:
    """P0.5: 创建带并发限制的 AsyncIOScheduler。

    集中管理 scheduler 配置:
    - AsyncIOExecutor: 单线程异步 (天然限制并发)
    - job_defaults.max_instances=1: 同一 job 不重叠
    - job_defaults.coalesce=True: 错过合并
    """
    return AsyncIOScheduler(
        timezone="UTC",
        executors={
            "default": AsyncIOExecutor(),
        },
        job_defaults={
            "max_instances": 1,
            "coalesce": True,
        },
    )

# v0.4.3: job→扩展域归属表 — 扩展关闭时对应 job 不调度
# (job_id 为 scheduler.py 中 add_job 的 id 参数)
_JOB_EXT_MAP: dict[str, str] = {
    "sync": "sync",                    # 跨端配置同步 (Mon 10:30)
    "cg_upstream_sync": "codegarden",  # 上游同步 (daily 09:00) — M1 核心
    "cg_service_scan": "codegarden_phase2b",  # 服务网格自动发现 (5min) — M2, P1.6
    "cg_event_process": "codegarden_phase2b",  # 事件总线处理 (60s) — M4, P1.6
    "cg_drift_assess": "tech_stack",   # 技术栈漂移评估 (3600s)
    "mitre_sync": "security_graph",    # MITRE ATT&CK 同步 (Sun 04:00)
    "cve_sync_to_security": "security_graph",  # CVE 同步到 security 实体 (1800s)
    "kl_pipeline_heartbeat": "secnews",  # KL 管线心跳消费 (60s) — SECNEWS Phase 1
    "secnews_liveness_sweep": "secnews",  # 书签存活三态批扫 (Sun 02:00 UTC) — S1-3
}


def _is_job_enabled(job_id: str) -> bool:
    """job 是否参与调度 — 无扩展归属的 job 永远启用。"""
    ext = _JOB_EXT_MAP.get(job_id)
    if ext is None:
        return True
    enabled = is_extension_enabled(ext)
    if not enabled:
        _logger.info(f"skipping job {job_id} (extension {ext} disabled)")
    return enabled


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
        self.scheduler: AsyncIOScheduler | None = None
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

        self.scheduler = create_scheduler()
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
        # v1.8 R3: 原 job 2/3/5 (trend_rebuild / url_content_check /
        # export_rebuild) 已收敛进 collect_all_job 尾部 post-ingest 链
        # Phase 3.5: job 4 — 来源信誉重算 (默认 6h; v0.4.0: 接线 config)
        self.scheduler.add_job(
            jobs.source_reputation_rebuild_job,
            trigger=IntervalTrigger(
                seconds=config.quality_reputation_interval_seconds,
                start_date=_now_utc,
            ),
            id="source_reputation_rebuild",
            name="source reputation rebuild",
            replace_existing=True,
        )
        # v1.8 R3: 原 job 5 (export_rebuild 每 30min) 已并入 collect_all 尾部
        # (main.py 启动时也会 rebuild 一次, 无新数据时无需重建)
        # Phase 42: job 6 — 跨端配置同步 (Q2 决策: 每周一 10:30 Asia/Shanghai)
        if _is_job_enabled("sync"):
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
        # P0 消费策略: job 10 — 自动消费者 (每日 02:30 Asia/Shanghai,
        # 在 compile_daily 之后运行): 消费 pending compile 任务 (规则式
        # 编译: 分类 + lifecycle 流转 + done) + 归档超龄积压。
        self.scheduler.add_job(
            jobs.consume_compile_tasks_job,
            trigger=CronTrigger(hour=2, minute=30, timezone=SHANGHAI_TZ),
            id="compile_consumer",
            name="knowledge compile consumer (daily 02:30)",
            replace_existing=True,
        )
        # v1.8 R3: 原 job 10 (compile_weekly, 周日 03:00) 已删除 — 与
        # compile_daily 重复注册同一函数, 周日会在 02:00/03:00 跑两次
        # v1.8 R3: 原 soul_weekly (Sun 04:00) / migrate_weekly (Sun 05:00) /
        # summary_weekly (Sun 06:00) 三个链式 cron 合并为单个周日维护 job
        self.scheduler.add_job(
            jobs.weekly_maintenance_job,
            trigger=CronTrigger(day_of_week="sun", hour=4, timezone=SHANGHAI_TZ),
            id="weekly_maintenance",
            name="weekly maintenance: soul -> migrate -> summary (Sun 04:00)",
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
        # P0.1 → v0.5 §18: job 13 — 7 天遥测窗口 (每周日 05:00 Asia/Shanghai)
        # quality_logs_cleanup_job 并入 telemetry_window_job: 同一注册点
        # 扩展为 WARM 层全部遥测表 (qcl 归档 / crawler_runs / raw_items
        # truncate), 策略由 retention.json ``scheduled_in`` 标签驱动。
        self.scheduler.add_job(
            jobs.telemetry_window_job,
            trigger=CronTrigger(day_of_week="sun", hour=5, timezone=SHANGHAI_TZ),
            id="telemetry_window",
            name="telemetry window 7d (Sun 05:00)",
            replace_existing=True,
        )
        # P1: job 14 — 每日数据库自动备份 (04:30 Asia/Shanghai, 避开
        # 02:00 compile / 02:30 consumer / 05:00 cleanup 时段)。
        # online backup API 对运行中服务安全; 保留最近 7 份自动清理。
        self.scheduler.add_job(
            jobs.daily_db_backup_job,
            trigger=CronTrigger(hour=4, minute=30, timezone=SHANGHAI_TZ),
            id="daily_db_backup",
            name="daily db backup (04:30)",
            replace_existing=True,
        )
        # Phase 2a CodeGarden: job 15 — 上游同步 (每日 09:00 Asia/Shanghai)
        if _is_job_enabled("cg_upstream_sync"):
            self.scheduler.add_job(
                jobs.cg_upstream_sync_job,
                trigger=CronTrigger(hour=9, timezone=SHANGHAI_TZ),
                id="cg_upstream_sync",
                name="codegarden upstream sync (daily 09:00)",
                replace_existing=True,
            )
        # Phase 2b CodeGarden: job 16 — 服务网格自动发现 (每 5 分钟)
        if _is_job_enabled("cg_service_scan"):
            self.scheduler.add_job(
                jobs.cg_service_scan_job,
                trigger=IntervalTrigger(seconds=300, start_date=_now_utc),
                id="cg_service_scan",
                name="codegarden service scan (every 5min)",
                replace_existing=True,
            )
        # Phase 2b CodeGarden: job 17 — 事件总线处理 (每 60 秒)
        if _is_job_enabled("cg_event_process"):
            self.scheduler.add_job(
                jobs.cg_event_process_job,
                trigger=IntervalTrigger(seconds=60, start_date=_now_utc),
                id="cg_event_process",
                name="codegarden event process (every 60s)",
                replace_existing=True,
            )
        # SECNEWS Phase 1 (2026-08-24): kl_queue 心跳消费 (每 60 秒) —
        # drain_due 常规消化 + 每 10 拍 sweep 兜底; 归属 secnews 扩展域。
        if _is_job_enabled("kl_pipeline_heartbeat"):
            self.scheduler.add_job(
                jobs.kl_pipeline_heartbeat_job,
                trigger=IntervalTrigger(seconds=60, start_date=_now_utc),
                id="kl_pipeline_heartbeat",
                name="kl pipeline heartbeat: drain due tasks (every 60s)",
                replace_existing=True,
            )
        # SECNEWS S1-3 (2026-08-24): 书签存活三态批扫 (每周日 02:00 UTC)。
        if _is_job_enabled("secnews_liveness_sweep"):
            self.scheduler.add_job(
                jobs.secnews_liveness_sweep_job,
                trigger=CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="UTC"),
                id="secnews_liveness_sweep",
                name="bookmark liveness sweep: alive/dead/unknown (Sun 02:00 UTC)",
                replace_existing=True,
            )
        # Phase 2 Security Graph: job 18 — MITRE ATT&CK 同步 (每周日 04:00 Asia/Shanghai)
        if _is_job_enabled("mitre_sync"):
            self.scheduler.add_job(
                jobs.mitre_sync_job,
                trigger=CronTrigger(day_of_week="sun", hour=4, minute=0, timezone="Asia/Shanghai"),
                id="mitre_sync",
                name="mitre attack sync (Sun 04:00)",
                replace_existing=True,
            )
        # v1.8 R3: 原 job 19 (security_enrichment 每 5min) 已并入
        # collect_all 尾部 post-ingest 链
        # v1.8 Phase 8: job 28 — 追抓 watchdog (每 60 秒)
        self.scheduler.add_job(
            jobs.catchup_watchdog_job,
            trigger=IntervalTrigger(seconds=60, start_date=_now_utc),
            id="catchup_watchdog",
            name="catchup watchdog (every 60s)",
            replace_existing=True,
        )
        # v1.8 Phase 8: job 29 — 死源复活 (每日 03:00 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.source_revival_check_job,
            trigger=CronTrigger(hour=3, minute=0, timezone=SHANGHAI_TZ),
            id="source_revival_check",
            name="source revival check (daily 03:00 Shanghai)",
            replace_existing=True,
        )
        # P1-1: job 30 — validation issues 自动归档 (每日 04:00 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.collect_validations_cleanup_job,
            trigger=CronTrigger(hour=4, minute=0, timezone=SHANGHAI_TZ),
            id="collect_validations_cleanup",
            name="collect validations cleanup (daily 04:00 Shanghai)",
            replace_existing=True,
        )
        # Phase 10: job 31 — KL T1 触发器 (kl:raw → kl:refine, 每 60s)
        self.scheduler.add_job(
            jobs.kl_trigger_t1_job,
            trigger=IntervalTrigger(seconds=60, start_date=_now_utc),
            id="kl_trigger_t1",
            name="KL T1 trigger: kl:raw -> kl:refine (every 60s)",
            replace_existing=True,
        )
        # Phase 10: job 32 — KL T2 触发器 (kl:refine → kl:link, 每 120s)
        self.scheduler.add_job(
            jobs.kl_trigger_t2_job,
            trigger=IntervalTrigger(seconds=120, start_date=_now_utc),
            id="kl_trigger_t2",
            name="KL T2 trigger: kl:refine -> kl:link (every 120s)",
            replace_existing=True,
        )
        # Phase 10: job 33 — 死信队列监控 (每 600s = 10min)
        self.scheduler.add_job(
            jobs.kl_dead_letter_retry_job,
            trigger=IntervalTrigger(seconds=600, start_date=_now_utc),
            id="kl_dead_letter_retry",
            name="KL dead letter monitor (every 10min)",
            replace_existing=True,
        )
        # Phase 12: job 34 — T3 触发器 (每 600s)
        self.scheduler.add_job(
            jobs.kl_trigger_t3_job,
            trigger=IntervalTrigger(seconds=600, start_date=_now_utc),
            id="kl_trigger_t3",
            name="KL T3 trigger: kl:link -> kl:structure (every 600s)",
            replace_existing=True,
        )
        # Phase 12: job 35 — T4 触发器 (每 1800s)
        self.scheduler.add_job(
            jobs.kl_trigger_t4_job,
            trigger=IntervalTrigger(seconds=1800, start_date=_now_utc),
            id="kl_trigger_t4",
            name="KL T4 trigger: kl:structure -> kl:publish (every 1800s)",
            replace_existing=True,
        )

        # Phase 13: job 36 — 规划动作检查 (每 600s)
        self.scheduler.add_job(
            jobs.planning_action_check_job,
            trigger=IntervalTrigger(seconds=600, start_date=_now_utc),
            id="planning_action_check",
            name="planning action check (every 600s)",
            replace_existing=True,
        )

        # Phase 14: job 38 — 技术栈漂移评估 (每小时)
        if _is_job_enabled("cg_drift_assess"):
            self.scheduler.add_job(
                jobs.cg_drift_assess_job,
                trigger=IntervalTrigger(seconds=3600, start_date=_now_utc),
                id="cg_drift_assess",
                name="codegarden tech stack drift assess (every 3600s)",
                replace_existing=True,
            )

        # Phase 14: job 39 — CVE 同步 (每 30 分钟)
        if _is_job_enabled("cve_sync_to_security"):
            self.scheduler.add_job(
                jobs.cve_sync_to_security_job,
                trigger=IntervalTrigger(seconds=1800, start_date=_now_utc),
                id="cve_sync_to_security",
                name="CVE sync to security entities (every 1800s)",
                replace_existing=True,
            )

        # v0.5 M3.5: job — wiki_archiver (每日 03:50 Asia/Shanghai)
        # 30 天自动归档到 llm-wiki-2.0/items/ + sources/ + retention.json
        self.scheduler.add_job(
            jobs.wiki_archiver_job,
            trigger=CronTrigger(hour=3, minute=50, timezone=SHANGHAI_TZ),
            id="wiki_archiver",
            name="wiki archiver 30d (daily 03:50 Shanghai)",
            replace_existing=True,
        )

        # v0.5 M3.5: job — retention_decay (每周日 05:30 Asia/Shanghai,
        # 紧跟 05:00 telemetry_window)
        self.scheduler.add_job(
            jobs.retention_decay_job,
            trigger=CronTrigger(day_of_week="sun", hour=5, minute=30, timezone=SHANGHAI_TZ),
            id="retention_decay",
            name="retention Ebbinghaus decay (Sun 05:30 Shanghai)",
            replace_existing=True,
        )

        # Phase 17: job — attention 聚合 (每 30 分钟)
        self.scheduler.add_job(
            jobs.attention_aggregate_job,
            trigger=IntervalTrigger(seconds=1800, start_date=_now_utc),
            id="attention_aggregate",
            name="attention event aggregation (every 1800s)",
            replace_existing=True,
        )

        # Phase 1.4 (Crawler v2): job — 标讯过期检查 (每 30 分钟)
        self.scheduler.add_job(
            jobs.bid_expiry_check_job,
            trigger=IntervalTrigger(seconds=1800, start_date=_now_utc),
            id="bid_expiry_check",
            name="bid expiry check (every 1800s)",
            replace_existing=True,
        )

        # Phase 2.2 (Crawler v2): job — URL 全量校验 (每 5 分钟)
        self.scheduler.add_job(
            jobs.url_full_check_job,
            trigger=IntervalTrigger(seconds=300, start_date=_now_utc),
            id="url_full_check",
            name="URL full check (every 300s)",
            replace_existing=True,
        )

        # P1-5: job — 知识分类消费提速 (每 30 分钟, 500 条/批)
        self.scheduler.add_job(
            jobs.knowledge_classify_job,
            trigger=IntervalTrigger(seconds=1800, start_date=_now_utc),
            id="knowledge_classify",
            name="knowledge classify unclassified items (every 1800s)",
            replace_existing=True,
        )

        # P3-4: job — 内容草稿生成 (每 6 小时)
        self.scheduler.add_job(
            jobs.content_draft_generation_job,
            trigger=IntervalTrigger(seconds=21600, start_date=_now_utc),
            id="content_draft_generation",
            name="content draft generation from published items (every 21600s)",
            replace_existing=True,
        )

        # 遗留项: job — 知识库空壳条目补全 (每 6 小时, 20 条/批)
        self.scheduler.add_job(
            jobs.knowledge_stub_backfill_job,
            trigger=IntervalTrigger(seconds=21600, start_date=_now_utc),
            id="knowledge_stub_backfill",
            name="knowledge stub backfill from URLs (every 21600s)",
            replace_existing=True,
        )

        # v0.4 收尾: job — knowledge_chunks 段落切分生成 (每 30 分钟)
        self.scheduler.add_job(
            jobs.knowledge_chunk_generation_job,
            trigger=IntervalTrigger(seconds=1800, start_date=_now_utc),
            id="knowledge_chunk_generation",
            name="knowledge chunk generation (every 1800s)",
            replace_existing=True,
        )

        # v0.4 收尾: job — security↔knowledge 实体统一 (每 10 分钟)
        self.scheduler.add_job(
            jobs.security_entity_concept_sync_job,
            trigger=IntervalTrigger(seconds=600, start_date=_now_utc),
            id="security_entity_concept_sync",
            name="security entity ↔ knowledge concept sync (every 600s)",
            replace_existing=True,
        )

        # Phase 3: job — 源级调度器 tick (每 60s)
        self.scheduler.add_job(
            jobs.source_scheduler_tick_job,
            trigger=IntervalTrigger(seconds=60, start_date=_now_utc),
            id="source_scheduler_tick",
            name="source scheduler tick (every 60s)",
            replace_existing=True,
        )

        # Phase 3: job — 死源探活 (每日 03:30 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.source_probe_job,
            trigger=CronTrigger(hour=3, minute=30, timezone=SHANGHAI_TZ),
            id="source_probe",
            name="dead source probe (daily 03:30 Shanghai)",
            replace_existing=True,
        )

        # Phase 3: job — 源级告警评估 (每 300s)
        self.scheduler.add_job(
            jobs.source_alert_eval_job,
            trigger=IntervalTrigger(seconds=300, start_date=_now_utc),
            id="source_alert_eval",
            name="source alert evaluation (every 300s)",
            replace_existing=True,
        )

        # v1.7 Phase 5 — Agent 集成与双向环
        # Phase 7 Option A 简化: 移除 agent_task_consumer / kv_cache_cleanup 两个 job
        # v1.8 R3: 原 job 21 (auto_extract) + job 22 (alert_evaluator) 合并
        # 为单个 60s job (同节奏、同扫描对象, 顺序执行)
        self.scheduler.add_job(
            jobs.auto_extract_alert_job,
            trigger=IntervalTrigger(seconds=60, start_date=_now_utc),
            id="auto_extract_alert",
            name="auto extract tags + alert evaluator (every 60s)",
            replace_existing=True,
        )
        # v1.8: 原 job 23 (review_scheduler) / job 24 (profile_updater) 为 NoOp
        # 占位, 已删除 —— 复习由前端 /api/reviews/due 驱动, profile 由事件实时写入
        # job 25: 每日简报生成 (08:00 Shanghai)
        self.scheduler.add_job(
            jobs.digest_generator_job,
            trigger=CronTrigger(hour=8, minute=0, timezone=SHANGHAI_TZ),
            id="digest_generator",
            name="daily digest generator (08:00 Shanghai)",
            replace_existing=True,
        )
        # job 26: 数据源健康检查 (15min)
        self.scheduler.add_job(
            jobs.source_health_check_job,
            trigger=IntervalTrigger(seconds=900, start_date=_now_utc),
            id="source_health_check",
            name="source health check (every 15min)",
            replace_existing=True,
        )
        # v1.8 R3: 原 job 27 (fts_rebuild 每 5min 全量重建) 已并入
        # collect_all 尾部 post-ingest 链 — 无新数据时全量重建 FTS 纯属浪费
        # job 28: Profile 衰减 (03:00 Shanghai)
        self.scheduler.add_job(
            jobs.profile_decay_job,
            trigger=CronTrigger(hour=3, minute=0, timezone=SHANGHAI_TZ),
            id="profile_decay",
            name="profile weight decay (03:00 Shanghai)",
            replace_existing=True,
        )
        # Phase 7: kv_cache_cleanup_job 已从 scheduler 中移除 (kv_cache_service 删除)
        # Phase 7: agent_task_consumer_job 已从 scheduler 中移除 (内部 agent 删除)

        # v0.4.3 复利驱动器②: SM-2 每日复习推送 (每天 08:00 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.sm2_daily_push_job,
            trigger=CronTrigger(hour=8, minute=0, timezone=SHANGHAI_TZ),
            id="sm2_daily_push",
            name="SM-2 daily review push (08:00 Shanghai)",
            replace_existing=True,
            misfire_grace_time=300,
        )
        # v0.4.3 复利驱动器③: 知识地图每日重建 (每天 02:00 Asia/Shanghai)
        self.scheduler.add_job(
            jobs.map_rebuild_daily_job,
            trigger=CronTrigger(hour=2, minute=0, timezone=SHANGHAI_TZ),
            id="map_rebuild_daily",
            name="knowledge map daily rebuild (02:00 Shanghai)",
            replace_existing=True,
            misfire_grace_time=600,
        )

        self.scheduler.start()
        self.logger.info(
            f"scheduler started, {len(self.scheduler.get_jobs())} jobs "
            f"(collect_all every {self._interval}s + post-ingest 链: "
            f"trend/fts/enrichment/url_check/export)"
        )
        # 注册到模块级 singleton
        set_scheduler(self)
        # 启动后立即异步触发一次 collect_all
        asyncio.get_event_loop().create_task(self._run_initial())

    async def _run_initial(self) -> None:
        """启动后延迟 5s 执行首次采集 + 跨端同步 catch-up 检查"""
        await asyncio.sleep(5)
        await jobs.collect_all_job()
        # Phase 42: 启动 catch-up (Q2 决策; v0.4.3: sync 扩展关闭时跳过)
        if not _is_job_enabled("sync"):
            self.logger.info("sync extension disabled, skipping catch-up check")
            return
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

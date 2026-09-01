"""APScheduler 调度的 job 函数（v0.6 P0-③ 自单文件拆分为按域包）。

These are thin async functions invoked by
:class:`backend.scheduler.scheduler.HotspotScheduler`. They delegate the
real work to services 层 — the scheduler itself is just a timing layer.

The ``CollectionService`` instance is injected at scheduler start time
via :func:`set_service`; this avoids a module-level import cycle between
``backend.scheduler`` and ``backend.services``.

拆分布局（空壳门面策略，方案 §9）：
- ``_runtime``   注入状态（_service）+ SSE 插桩（job_done_event/instrument_job）
- ``collect``    采集 / 同步 / 源健康 / watchdog / alert 链
- ``kl``         kl_queue 触发器 / 死信 / 心跳 / 存活扫描
- ``codegarden`` cg_* 扩展域 job（feature gate）
- ``security``   MITRE / 安全富化 / CVE / 实体概念同步
- ``knowledge``  分类 / 抽取 / 草稿 / chunk / wiki 归档
- ``digest``     简报 / 快照 / 周报 / 编译 / SOUL / SM-2
- ``maintenance``趋势重建 / 备份 / FTS / 衰减 / 各类清理

契约保证：本 ``__init__`` 重导出全部公开名，``from backend.scheduler.jobs
import X``、``jobs.X`` 与 ``patch("backend.scheduler.jobs.X")`` 行为与拆分前
一致；``_service`` 经模块 ``__getattr__`` 活委托到 ``_runtime``。跨域 job 调用
在各域内经 ``_jobs_pkg.<fn>`` 动态解析。
"""

from backend.scheduler.jobs._runtime import (
    instrument_job,
    job_done_event,
    reset_service,
    set_service,
)
from backend.scheduler.jobs.collect import (
    _classify_new_items,
    alert_evaluator_job,
    auto_extract_alert_job,
    catchup_watchdog_job,
    collect_all_job,
    collect_validations_cleanup_job,
    should_run_catchup,
    source_alert_eval_job,
    source_health_check_job,
    source_probe_job,
    source_revival_check_job,
    source_scheduler_tick_job,
    sync_job,
    url_content_check_job,
    url_full_check_job,
)
from backend.scheduler.jobs.kl import (
    _KL_SWEEP_EVERY_N_BEATS,
    _kl_heartbeat_beats,
    kl_dead_letter_retry_job,
    kl_pipeline_heartbeat_job,
    kl_trigger_t1_job,
    kl_trigger_t2_job,
    kl_trigger_t3_job,
    kl_trigger_t4_job,
    secnews_liveness_sweep_job,
)
from backend.scheduler.jobs.codegarden import (
    cg_drift_assess_job,
    cg_event_process_job,
    cg_service_scan_job,
    cg_upstream_sync_job,
)
from backend.scheduler.jobs.security import (
    cve_sync_to_security_job,
    mitre_sync_job,
    secrets_rotation_check_job,
    security_enrichment_job,
    security_entity_concept_sync_job,
)
from backend.scheduler.jobs.knowledge import (
    auto_extract_job,
    content_draft_generation_job,
    knowledge_chunk_generation_job,
    knowledge_classify_job,
    knowledge_stub_backfill_job,
    scheduled_migrate_job,
    wiki_archiver_job,
)
from backend.scheduler.jobs.digest import (
    consume_compile_tasks_job,
    daily_snapshot_job,
    digest_generator_job,
    sm2_daily_push_job,
    scheduled_compile_job,
    scheduled_soul_job,
    scheduled_summary_job,
    weekly_report_job,
)
from backend.scheduler.jobs.maintenance import (
    _force_full_backup_rotate,
    attention_aggregate_job,
    bid_expiry_check_job,
    daily_db_backup_job,
    db_diet_job,
    export_rebuild_job,
    fts_rebuild_job,
    map_rebuild_daily_job,
    observability_aggregator_job,
    observability_threshold_check_job,
    observability_ttl_job,
    planning_action_check_job,
    profile_decay_job,
    retention_decay_job,
    source_reputation_rebuild_job,
    scheduled_stats_job,
    telemetry_window_job,
    trend_rebuild_job,
    weekly_maintenance_job,
    wiki_items_fts_sync_job,
)


def __getattr__(name: str):
    """活委托：``_service`` 由 scheduler 运行期注入到 ``_runtime``。

    模块属性读取时才取值，避免 ``from ... import _service`` 快照旧值。
    """
    if name == "_service":
        from backend.scheduler.jobs import _runtime

        return _runtime._service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # 存量 bug 清扫补齐 (此前 import 了但 __all__ 漏登记, *-import 拿不到):
    "auto_extract_alert_job",
    "cg_event_process_job",
    "cg_service_scan_job",
    "cg_upstream_sync_job",
    "collect_all_job",
    "consume_compile_tasks_job",
    "daily_db_backup_job",  # P1: 每日数据库自动备份
    "daily_snapshot_job",
    "db_diet_job",
    "export_rebuild_job",
    "instrument_job",
    "job_done_event",
    "map_rebuild_daily_job",
    "mitre_sync_job",
    "reset_service",
    "scheduled_compile_job",
    "scheduled_migrate_job",
    "scheduled_soul_job",
    "scheduled_stats_job",
    "scheduled_summary_job",
    "secrets_rotation_check_job",
    "security_enrichment_job",
    "set_service",
    "should_run_catchup",
    "sm2_daily_push_job",
    "source_reputation_rebuild_job",
    "sync_job",
    "telemetry_window_job",  # v0.5 §18: 7 天遥测窗口
    "trend_rebuild_job",
    "url_content_check_job",
    "weekly_maintenance_job",
    "weekly_report_job",
    "wiki_items_fts_sync_job",
]
__all__.extend([
    "alert_evaluator_job",
    "auto_extract_job",
    "collect_validations_cleanup_job",  # P1-1: validation 自动归档
    "digest_generator_job",
    "fts_rebuild_job",
    "profile_decay_job",
    "source_alert_eval_job",
    "source_health_check_job",
    "source_probe_job",
    "source_revival_check_job",  # v1.8 Phase 8: 死源复活
    "source_scheduler_tick_job",
])
__all__.extend([
    "attention_aggregate_job",
    "bid_expiry_check_job",
    "catchup_watchdog_job",
    "cg_drift_assess_job",
    "content_draft_generation_job",
    "cve_sync_to_security_job",
    "kl_dead_letter_retry_job",
    "kl_pipeline_heartbeat_job",
    "kl_trigger_t1_job",
    "kl_trigger_t2_job",
    "kl_trigger_t3_job",
    "kl_trigger_t4_job",
    "knowledge_chunk_generation_job",
    "knowledge_classify_job",
    "knowledge_stub_backfill_job",
    "observability_aggregator_job",  # v0.7 Batch ③: api_events → api_metrics_hourly roll-up
    "observability_threshold_check_job",  # v0.7 Batch ④: 阈值规则引擎
    "observability_ttl_job",  # v0.7 Batch 1: 观测表 TTL 清理
    "planning_action_check_job",
    "retention_decay_job",
    "secnews_liveness_sweep_job",
    "security_entity_concept_sync_job",
    "url_full_check_job",
    "wiki_archiver_job",
])

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


async def cg_upstream_sync_job() -> None:
    """Phase 2a CodeGarden: 每日 09:00 (Asia/Shanghai) 触发 fork 类型项目的上游同步。

    遍历所有 source_type=fork 且有 upstream_url 的 cg_projects,
    为每个项目创建一个 project_sync 任务到 knowledge_tasks 队列。
    实际同步由 watchdog 或 TaskExecutor 执行, 这里只负责调度。

    失败只 log.error, 不抛异常 (与既有 job 模式一致)。
    """
    try:
        from backend.repository.codegarden_repo import CodegardenProjectRepository
        from backend.services.codegarden_project_service import CodegardenProjectService

        repo = CodegardenProjectRepository()
        svc = CodegardenProjectService()
        # 列出所有 fork 项目 (不含 archived/deprecated)
        projects, total = await asyncio.to_thread(
            repo.list, source_type="fork", limit=500
        )
        created = 0
        for p in projects:
            if not p.get("upstream_url"):
                continue
            try:
                await asyncio.to_thread(svc.request_upstream_sync, p["id"])
                created += 1
            except Exception as e:
                _logger.warning(
                    f"cg_upstream_sync_job: project {p['id']} sync request failed: {e}"
                )
        _logger.info(f"cg_upstream_sync_job: scanned {total} fork projects, created {created} sync tasks")
    except Exception as e:
        _logger.error(f"cg_upstream_sync_job crashed: {e}")


# ============================================================================
# Phase 2b CodeGarden: job 16 — 服务网格自动发现 (每 5 分钟)
# ============================================================================
async def cg_service_scan_job() -> None:
    """Phase 2b CodeGarden: 每 5 分钟扫描本机服务 (lsof + docker + pm2) upsert 到 cg_services."""
    try:
        from backend.services.codegarden_service_service import CodegardenServiceService
        svc = CodegardenServiceService()
        result = await asyncio.to_thread(svc.scan_local_services)
        _logger.info(
            f"cg_service_scan_job: scanned={result['scanned']} "
            f"created={result['created']} updated={result['updated']}"
        )
    except Exception as e:
        _logger.error(f"cg_service_scan_job crashed: {e}")


# ============================================================================
# Phase 2b CodeGarden: job 17 — 事件总线处理 (每 60 秒)
# ============================================================================
async def cg_event_process_job() -> None:
    """Phase 2b CodeGarden: 每 60 秒处理 pending 事件.

    当前处理逻辑 (Phase 2b MVP):
    - port_conflict: 检查端口是否仍冲突, 标记 processed
    - 其他事件类型: 直接标记 processed (无 handler)
    - 异常: 标记 failed + error_message
    """
    try:
        from backend.repository.codegarden_orchestration_repo import (
            CodegardenEventRepository,
        )
        repo = CodegardenEventRepository()
        pending = await asyncio.to_thread(repo.list_pending, 50)
        if not pending:
            return

        processed = 0
        failed = 0
        for event in pending:
            try:
                # MVP: 所有事件类型直接标记成功 (实际 handler 后续 Phase 实现)
                # TODO Phase 2c+: 按 event_type 分发到具体 handler
                await asyncio.to_thread(repo.mark_processed, event["id"], success=True)
                processed += 1
            except Exception as e:
                await asyncio.to_thread(
                    repo.mark_processed, event["id"],
                    success=False, error_message=str(e),
                )
                failed += 1
                _logger.warning(
                    f"cg_event_process_job: event {event['id']} failed: {e}"
                )
        _logger.info(
            f"cg_event_process_job: pending={len(pending)} "
            f"processed={processed} failed={failed}"
        )
    except Exception as e:
        _logger.error(f"cg_event_process_job crashed: {e}")


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
    "cg_upstream_sync_job",
    "cg_service_scan_job",
    "cg_event_process_job",
    "mitre_sync_job",
    "security_enrichment_job",
]


# ============================================================================
# Phase 2 Security Graph: job 18 — MITRE ATT&CK 同步 (每周日 04:00 Asia/Shanghai)
# ============================================================================
async def mitre_sync_job() -> None:
    """Phase 2: 每周同步 MITRE ATT&CK STIX 数据到 security_entities + security_edges。

    触发条件
    --------
    - scheduler 每周日 04:00 Asia/Shanghai 触发
    - 失败只 log.error，不抛异常（与既有 job 模式一致）

    注意
    ----
    - 首次同步建议手动触发 /api/security/mitre/sync (clear=True)
    - 后续增量同步由 clear=False 控制
    """
    try:
        from backend.security.mitre_attack import MitreAttackClient

        client = MitreAttackClient()
        count = await asyncio.to_thread(client.sync_to_db, clear=False)
        _logger.info(f"mitre_sync_job: synced {count} entities")
    except Exception as e:
        _logger.error(f"mitre_sync_job crashed: {e}")


# ============================================================================
# Phase 3 Security Graph: job 19 — security enrichment (每 300 秒)
# ============================================================================
async def security_enrichment_job() -> None:
    """Phase 3: 每 300s 扫描近 24h 未 enrichment 的 hotspot items，异步 enrichment.

    不阻塞采集主路径，独立 job 运行。
    """
    try:
        from backend.security.enricher import enrich_batch
        from backend.repository.db import get_connection
        from backend.domain.security_models import _now_iso

        conn = get_connection()
        # 查询近 24h 且尚未 enrichment 的 hotspot items
        rows = conn.execute(
            "SELECT id, title, summary FROM hotspots "
            "WHERE datetime(published_at) >= datetime('now', '-24 hours') "
            "AND (cve_ids IS NULL AND attack_techniques IS NULL AND compliance_refs IS NULL)"
            "LIMIT 200"
        ).fetchall()
        if not rows:
            return

        items = [dict(r) for r in rows]
        enriched = enrich_batch(items)
        if not enriched:
            return

        now = _now_iso()
        count = 0
        for e in enriched:
            eid = e.get("id")
            if not eid:
                continue
            sets = []
            params = []
            for field in ("cve_ids", "attack_techniques", "compliance_refs"):
                val = e.get(field)
                if val:
                    sets.append(f"{field} = COALESCE({field}, '[]') || ',' || ?")
                    params.append(val)
            if sets:
                sets.append("updated_at = ?")
                params.append(now)
                params.append(eid)
                conn.execute(
                    f"UPDATE knowledge_items SET {', '.join(sets)} WHERE id = ?",
                    params,
                )
                count += 1

        _logger.info(f"security_enrichment_job: processed {len(rows)} items, enriched {count}")
    except Exception as e:
        _logger.error(f"security_enrichment_job crashed: {e}")


# ============================================================================
# v1.7 Phase 5: Agent 集成与双向环 — 10 个新 job
# ============================================================================

async def agent_task_consumer_job() -> None:
    """v1.7 Phase 5: 消费信号 — 把 lifecycle=signal 的 hotspots 创建为 extract 任务.

    60s 间隔: signal 文章进入待提取队列, 供外部 Agent 处理.
    """
    try:
        from backend.services.agent_task_service import create_task

        def _scan():
            from backend.repository.db import get_connection
            conn = get_connection()
            rows = conn.execute(
                "SELECT id FROM hotspots "
                "WHERE lifecycle = 'signal' OR lifecycle IS NULL "
                "ORDER BY ingested_at DESC LIMIT 10"
            ).fetchall()
            return [r["id"] for r in rows]

        ids = await asyncio.to_thread(_scan)
        created = 0
        for hid in ids:
            # 避免重复: 查是否已有 pending
            def _has_pending(hid: str) -> bool:
                from backend.repository.knowledge_repo import knowledge_repo
                tasks = knowledge_repo.list_tasks_by_type(
                    "extract", params_filter={"target_id": hid}
                )
                return any(t["status"] == "pending" for t in tasks)

            if await asyncio.to_thread(_has_pending, hid):
                continue
            await asyncio.to_thread(
                create_task, "extract", "hotspot", hid, 1
            )
            created += 1

        if created:
            _logger.info(f"agent_task_consumer_job: created {created} extract tasks")
    except Exception as e:
        _logger.error(f"agent_task_consumer_job crashed: {e}")


async def auto_extract_job() -> None:
    """v1.7 Phase 5: 同步执行 (无 Agent 时) 的简单标签提取.

    60s 间隔: 对未提取的 hotspot 调 extract_tags, 写入 tags + hotspot_tags.
    作为 agent_task_consumer_job 的同步回退路径.
    """
    try:
        from backend.services.extract_service import extract_tags
        from backend.repository.tags_repo import TagRepository
        from backend.repository.db import get_connection

        def _scan_and_extract():
            conn = get_connection()
            # 找未提取的 hotspot (无关联 tags)
            rows = conn.execute(
                "SELECT h.id, h.title, h.summary, h.category "
                "FROM hotspots h "
                "WHERE NOT EXISTS (SELECT 1 FROM hotspot_tags ht WHERE ht.hotspot_id = h.id) "
                "AND h.summary IS NOT NULL "
                "ORDER BY h.ingested_at DESC LIMIT 20"
            ).fetchall()
            return [dict(r) for r in rows]

        items = await asyncio.to_thread(_scan_and_extract)
        tag_repo = TagRepository()
        extracted = 0
        for item in items:
            tags = extract_tags(item.get("summary") or "", item.get("title") or "", item.get("category") or "")
            for t in tags:
                tag_id = t.get("tag_id") or t.get("id")
                if not tag_id:
                    continue
                confidence = float(t.get("confidence", 0.5))
                try:
                    # ensure tag
                    existing = tag_repo.get(tag_id)
                    if existing is None:
                        tag_repo.add(
                            tag_id, tag_id, "technique",
                            weight=confidence, description=tag_id,
                        )
                    tag_repo.attach(item["id"], tag_id, confidence=confidence)
                except Exception as e:
                    _logger.warning(f"auto_extract: tag {tag_id} failed: {e}")
            extracted += 1

        if extracted:
            _logger.info(f"auto_extract_job: extracted {extracted} hotspots")
    except Exception as e:
        _logger.error(f"auto_extract_job crashed: {e}")


async def alert_evaluator_job() -> None:
    """v1.7 Phase 5: 对新 hotspot 跑告警评估.

    60s 间隔: 复用 evaluate_hotspot 对近期未评估 hotspot 跑规则匹配.
    """
    try:
        from backend.services.alert_service import evaluate_hotspot
        from backend.repository.db import get_connection

        def _scan():
            conn = get_connection()
            rows = conn.execute(
                "SELECT id FROM hotspots "
                "WHERE ingested_at >= datetime('now', '-1 day') "
                "ORDER BY ingested_at DESC LIMIT 50"
            ).fetchall()
            return [r["id"] for r in rows]

        ids = await asyncio.to_thread(_scan)
        evaluated = 0
        for hid in ids:
            try:
                await asyncio.to_thread(evaluate_hotspot, hid)
                evaluated += 1
            except Exception as e:
                _logger.warning(f"alert_evaluator: hotspot {hid} failed: {e}")

        if evaluated:
            _logger.info(f"alert_evaluator_job: evaluated {evaluated} hotspots")
    except Exception as e:
        _logger.error(f"alert_evaluator_job crashed: {e}")


async def review_scheduler_job() -> None:
    """v1.7 Phase 5: SM-2 复习预检 (NoOp, 前端 /api/reviews/due 驱动)."""
    # 实际复习由前端 /api/reviews/due 实时驱动, 此 job 仅占位
    # Phase 6 可添加: 每日 09:00 检查到期 review, 通过 SSE 推送提醒
    return None


async def profile_updater_job() -> None:
    """v1.7 Phase 5: 个性化画像实时更新 (NoOp, 阅读事件已实时写入).

    profile 信号 (read/favorite/skip) 由事件触发 apply_signal, 本 job 不重复.
    """
    return None


async def digest_generator_job() -> None:
    """v1.7 Phase 5: 每日 08:00 Shanghai 生成昨日简报."""
    try:
        from backend.services.digest_service import generate_daily_digest
        result = await asyncio.to_thread(generate_daily_digest, 3)
        _logger.info(
            f"digest_generator_job: digest_id={result.get('id')} count={result.get('count')}"
        )
    except Exception as e:
        _logger.error(f"digest_generator_job crashed: {e}")


async def source_health_check_job() -> None:
    """v1.7 Phase 5: 数据源健康检查 (15min)."""
    try:
        from backend.services.source_health_service import check_all_health
        results = await asyncio.to_thread(check_all_health)
        red = sum(1 for r in results if r.get("status") == "red")
        yellow = sum(1 for r in results if r.get("status") == "yellow")
        if red or yellow:
            _logger.warning(
                f"source_health_check_job: red={red} yellow={yellow}"
            )
    except Exception as e:
        _logger.error(f"source_health_check_job crashed: {e}")


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


async def profile_decay_job() -> None:
    """v1.7 Phase 5: 每日 03:00 Shanghai 衰减所有 profile 权重."""
    try:
        from backend.services.profile_service import decay_all
        n = await asyncio.to_thread(decay_all)
        _logger.info(f"profile_decay_job: decayed {n} entries")
    except Exception as e:
        _logger.error(f"profile_decay_job crashed: {e}")


async def kv_cache_cleanup_job() -> None:
    """v1.7 Phase 5: 清理过期 KV 缓存 (30min)."""
    try:
        from backend.services.kv_cache_service import kv_cache
        cleaned = await asyncio.to_thread(kv_cache.cleanup_expired)
        if cleaned:
            _logger.info(f"kv_cache_cleanup_job: cleaned {cleaned} entries")
    except Exception as e:
        _logger.error(f"kv_cache_cleanup_job crashed: {e}")


# 更新 __all__
__all__.extend([
    "agent_task_consumer_job",
    "auto_extract_job",
    "alert_evaluator_job",
    "review_scheduler_job",
    "profile_updater_job",
    "digest_generator_job",
    "source_health_check_job",
    "fts_rebuild_job",
    "profile_decay_job",
    "kv_cache_cleanup_job",
])

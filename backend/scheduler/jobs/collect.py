"""collect 域 scheduler job (v0.6 P0-③ 自 jobs.py 按域拆分)。
实现为搬运原文；跨域 job 调用经包命名空间动态解析以保住
patch("backend.scheduler.jobs.<fn>") 测试契约。
"""
import asyncio
from datetime import datetime, timezone

import backend.scheduler.jobs as _jobs_pkg
from backend.logging_config import logger

_logger = logger.bind(component="jobs")


async def collect_all_job() -> None:
    """周期性执行完整采集 + post-ingest 链。

    v1.8 R3: trend_rebuild / fts_rebuild / security_enrichment /
    url_content_check / export_rebuild 从 5 个独立定时 job 收敛为采集
    尾部链式执行 — 这些都是「数据变更后才有意义」的重建/检查, 独立
    定时在无新数据时纯属空转。采集失败时跳过链 (数据未变)。
    """
    if _jobs_pkg._service is None:
        _logger.error("service not initialized, skipping collect_all_job")
        return
    try:
        report = await _jobs_pkg._service.run_once()
        _logger.info(
            f"collect_all_job: total={report.total}, "
            f"success={report.success_count}, failed={report.failed_count}, "
            f"duration={report.duration_ms}ms"
        )
    except Exception as e:
        _logger.error(f"collect_all_job crashed: {e}")
        return
    # ---- post-ingest 链 (各 job 内部自带异常隔离, 不会中断彼此) ----
    await _jobs_pkg.trend_rebuild_job()
    await _jobs_pkg.fts_rebuild_job()
    await _jobs_pkg.security_enrichment_job()
    await url_content_check_job()
    await _jobs_pkg.export_rebuild_job()
    # ---- 复利驱动器①: 即时分类 (不等待 30min 周期) ----
    await _classify_new_items()


async def _classify_new_items() -> None:
    """采集 tail 后即时分类新 items（复利驱动器①）。

    P0.4: 只更新 DB, 不回写 md。分类是自动化中间状态, md 只由用户/编译器写。
    只处理最近 5 分钟入库且未分类的条目 (上限 50), 同步 SQL 放 thread pool
    避免阻塞 event loop; 异常隔离不影响采集。
    """
    try:
        from backend.repository.db import get_connection
        from backend.repository.knowledge_repo import knowledge_repo
        from backend.services.auto_classifier import batch_classify

        def _run() -> int:
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, title, tags, source_url, domain, type, difficulty "
                "FROM knowledge_items "
                "WHERE (domain IS NULL OR type IS NULL OR difficulty IS NULL) "
                "AND ingested_at > datetime('now', '-5 minutes', 'utc') "
                "ORDER BY ingested_at ASC LIMIT 50"
            ).fetchall()
            if not rows:
                return 0
            items = [dict(r) for r in rows]
            classified = batch_classify(items)
            updated = 0
            for d in classified:
                item_id = d.get("id")
                if not item_id:
                    continue
                db_item = knowledge_repo.get_item(item_id)
                if db_item is None:
                    continue
                changed = False
                for field, key in (("domain", "domain"), ("type", "type"),
                                   ("difficulty", "difficulty"), ("topic", "topic")):
                    if d.get(key) and not getattr(db_item, field, None):
                        setattr(db_item, field, d[key])
                        changed = True
                if not changed:
                    continue
                # P0.4: 只更新 DB, 不回写 md (分类是中间状态)
                knowledge_repo.upsert_item(db_item)
                updated += 1
            return updated

        count = await asyncio.to_thread(_run)
        if count:
            _logger.info(f"_classify_new_items: {count} items classified")
    except Exception as e:
        _logger.error(f"_classify_new_items crashed: {e}")


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
    from datetime import datetime

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
    # P0-1: 解锁状态是 30 分钟 TTL (secrets_service.UNLOCK_TTL_SECONDS),
    # 而自动同步是每周一 10:30 触发 — 启动时 auto-unlock 的密钥早已过期。
    # 修复: 解锁过期时先尝试从持久化存储 (OS keyring / settings 表) 自动恢复,
    # 恢复成功即继续同步, 只有「无持久化密钥」才跳过并记录错误。
    if not force:
        ek = EncryptionKeyRepository().get_default()
        if ek is None or not _is_unlocked(ek.id):
            try:
                from backend.services.secrets_service import try_auto_unlock
                restored = try_auto_unlock()
            except Exception:
                restored = False
            if not restored or not _is_unlocked(ek.id):
                _logger.warning("sync_job: master_key 未解锁且无持久化密钥可恢复, 跳过同步")
                from backend.repository.sync_history_repo import SyncHistoryRepository
                SyncHistoryRepository().write(
                    config_id=cfg.id,
                    direction="bidirectional",
                    status="error",
                    error_message="master_key 未解锁且无法从 keychain/settings 自动恢复, 自动同步已跳过",
                    started_at=datetime.now(timezone.utc).isoformat(),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
                return
            _logger.info("sync_job: master_key 已从持久化存储自动恢复")

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


async def source_revival_check_job() -> None:
    """v1.8 Phase 8: 死源复活检查 (每日 03:00 Asia/Shanghai).

    流程
    ----
    1. 读 settings ``quality.revival_dead_for_days`` (默认 7)
    2. 列死源: status='dead' AND last_checked_at < now - N days
    3. 对每条源 HEAD 请求, 2xx/3xx 视为可达 → 标 active + zero_yield_runs=0
    4. 失败/异常: 保留 dead, 记 last_error + 更新 last_checked_at
    5. 写日志: revived=N, still_dead=M, error=K
    6. P1-2: 复活 ≥ 1 个 → 立即触发 1 次 auto catchup (since=now-24h),
       让复活源在下一个 collect_all 周期前就被实测

    注: 此 job 不主动跑全量 collect. 复活后, 下一个 collect_all
    (job 1, 每 5min) 会自然带这些源跑; P1-2 仅作为"立刻验证"加速.
    """
    try:
        from backend.services.source_revival_service import revive_all_dead

        results = await asyncio.to_thread(revive_all_dead)
        revived_count = 0
        if results:
            revived_count = sum(1 for r in results if r.status == "revived")
            still = sum(1 for r in results if r.status == "still_dead")
            error = sum(1 for r in results if r.status == "error")
            _logger.info(
                f"source_revival_check_job: total={len(results)} "
                f"revived={revived_count} still_dead={still} error={error}"
            )

        # P1-2: 复活了源, 立刻 enqueue 1 次 auto catchup 验证
        if revived_count >= 1:
            try:
                from datetime import datetime, timedelta, timezone

                from backend.services.catchup_service import (
                    mark_auto_enqueued,
                    should_enqueue_auto,
                )
                if should_enqueue_auto():
                    from backend.services.catchup_service import enqueue_catchup
                    since = (
                        datetime.now(timezone.utc) - timedelta(hours=24)
                    ).isoformat()
                    until = datetime.now(timezone.utc).isoformat()
                    run_id = await enqueue_catchup(
                        mode="auto",
                        since=since,
                        until=until,
                        categories=None,
                        max_per_source=20,
                    )
                    mark_auto_enqueued()
                    _logger.info(
                        f"source_revival_check_job: triggered auto catchup "
                        f"run_id={run_id} (revived={revived_count})"
                    )
                else:
                    _logger.info(
                        f"source_revival_check_job: revived={revived_count} "
                        f"but auto enqueue in debounce window, skip"
                    )
            except Exception as e:
                _logger.warning(
                    f"source_revival_check_job: post-revival catchup failed: {e}"
                )
    except Exception as e:
        _logger.error(f"source_revival_check_job crashed: {e}")


async def collect_validations_cleanup_job() -> None:
    """P1-1: 每日 04:00 Asia/Shanghai 归档旧 validation issues.

    7d 前的 unresolved issues 标 resolved_at=now, 防止表无限累积.
    不物理删除 — 保留历史, 供未来趋势分析.
    """
    try:
        from backend.services.collect_validator import auto_resolve_old_validations

        n = await asyncio.to_thread(auto_resolve_old_validations, older_than_days=7)
        if n > 0:
            _logger.info(
                f"collect_validations_cleanup_job: archived {n} stale issues "
                f"(older than 7 days)"
            )
        else:
            _logger.debug("collect_validations_cleanup_job: no stale issues")
    except Exception as e:
        _logger.error(f"collect_validations_cleanup_job crashed: {e}")


async def source_scheduler_tick_job() -> None:
    """Phase 3: 源级调度器 tick — 每 60s 查询待调度源并执行单源采集。

    委托 SourceSchedulerService.tick() 执行。
    失败只 log.error，不抛异常（与既有 job 模式一致）。
    """
    try:
        from backend.services.source_scheduler_service import (
            SourceSchedulerService,
            get_scheduler_service,
            set_scheduler_service,
        )

        svc = get_scheduler_service()
        if svc is None:
            # 首次调用时创建实例并注入 collection_service
            _svc = SourceSchedulerService()
            _svc.attach_collection_service(_jobs_pkg._service)
            set_scheduler_service(_svc)
            svc = _svc

        result = await svc.tick()
        if result["scheduled"] > 0:
            _logger.info(
                f"source_scheduler_tick_job: scheduled={result['scheduled']} "
                f"succeeded={result['succeeded']} failed={result['failed']} "
                f"skipped={result['skipped']}"
            )
    except Exception as e:
        _logger.error(f"source_scheduler_tick_job crashed: {e}")


async def source_probe_job() -> None:
    """Phase 3: 每日 03:30 Asia/Shanghai 对 dead 源执行 HEAD/GET 探测。

    委托 source_prober.probe_all_dead() 执行。
    失败只 log.error，不抛异常（与既有 job 模式一致）。
    """
    try:
        from backend.services.source_prober import probe_all_dead

        results = await asyncio.to_thread(probe_all_dead)
        alive = sum(1 for r in results if r["status"] == "alive")
        _logger.info(
            f"source_probe_job: probed {len(results)} dead sources, "
            f"alive={alive}"
        )
    except Exception as e:
        _logger.error(f"source_probe_job crashed: {e}")


async def source_alert_eval_job() -> None:
    """Phase 3: 每 300s 对所有活跃源检查告警规则。

    委托 SourceAlerter.evaluate_all() 执行。
    失败只 log.error，不抛异常（与既有 job 模式一致）。
    """
    try:
        from backend.services.source_alerter import SourceAlerter

        alerter = SourceAlerter()
        result = await asyncio.to_thread(alerter.evaluate_all)
        if result["alerts_triggered"] > 0:
            _logger.info(
                f"source_alert_eval_job: checked {result['sources_checked']} sources, "
                f"triggered {result['alerts_triggered']} alerts "
                f"(P1={result['alerts_by_level']['P1']}, P2={result['alerts_by_level']['P2']})"
            )
    except Exception as e:
        _logger.error(f"source_alert_eval_job crashed: {e}")


async def catchup_watchdog_job() -> None:
    """Phase 8: 每 60s 扫 collection_runs, 检测 started_at > 10min 未 finished 的孤儿.

    流程
    ----
    1. 查 ``finished_at IS NULL AND started_at < now-600s`` 的行
    2. 标 ``status='failed', error_msg='watchdog: timeout after 600s'``
    3. 若有孤儿, 防抖 (5min 内不重复) → enqueue 一次 auto catchup
       since=最早孤儿时刻, until=now, categories=all, max_per_source=30
    4. 更新 ``last_orphan_recovery_at`` 时间戳 (供 /api/health 暴露)

    失败只 log.error, 不抛异常 (与既有 job 模式一致).
    """
    from datetime import datetime, timedelta

    from backend.repository.db import get_connection
    from backend.services.catchup_service import (
        enqueue_catchup,
        mark_auto_enqueued,
        set_last_orphan_recovery_at,
        should_enqueue_auto,
    )

    try:
        conn = get_connection()
        # 1. 查孤儿 (started_at < now-600s, finished_at IS NULL)
        cutoff_iso = (
            datetime.now(timezone.utc) - timedelta(seconds=600)
        ).isoformat()
        stuck_rows = conn.execute(
            """
            SELECT id, started_at FROM collection_runs
            WHERE finished_at IS NULL AND started_at < ?
            ORDER BY started_at ASC
            """,
            (cutoff_iso,),
        ).fetchall()

        if not stuck_rows:
            # 无孤儿: 重置 recovery timestamp 不必要 (保留最近值)
            return

        # 2. 标记所有孤儿为 failed
        now_iso = datetime.now(timezone.utc).isoformat()
        stuck_ids = [int(r["id"]) for r in stuck_rows]
        for sid in stuck_ids:
            conn.execute(
                """
                UPDATE collection_runs
                SET finished_at = ?,
                    status = 'failed',
                    error_msg = 'watchdog: timeout after 600s'
                WHERE id = ? AND finished_at IS NULL
                """,
                (now_iso, sid),
            )
        logger.info(
            f"catchup_watchdog_job: marked {len(stuck_ids)} orphan runs as failed"
        )

        # 3. 防抖 + enqueue auto catchup
        earliest = min(r["started_at"] for r in stuck_rows)
        if should_enqueue_auto():
            try:
                run_id = await enqueue_catchup(
                    mode="auto",
                    since=earliest,
                    until=now_iso,
                    categories=None,  # all
                    max_per_source=30,
                )
                mark_auto_enqueued()
                set_last_orphan_recovery_at(now_iso)
                logger.info(
                    f"catchup_watchdog_job: enqueued auto catchup run_id={run_id} "
                    f"since={earliest} until={now_iso}"
                )
            except Exception as e:
                # enqueue 失败不阻塞 watchdog 主流程, 仅 log
                logger.error(
                    f"catchup_watchdog_job: enqueue auto catchup failed: {e}"
                )
                # 仍然记录恢复时间 (孤儿已标 failed)
                set_last_orphan_recovery_at(now_iso)
        else:
            # 在防抖窗口内, 仅标孤儿失败 + 更新 recovery timestamp
            set_last_orphan_recovery_at(now_iso)
            logger.info(
                f"catchup_watchdog_job: orphans={len(stuck_ids)} marked, "
                f"skip enqueue (within {300}s debounce window)"
            )
    except Exception as e:
        logger.error(f"catchup_watchdog_job crashed: {e}")


async def url_full_check_job() -> None:
    """Phase 2.2: 每 5 分钟对未校验条目做 URL 全量校验。

    查询最近 24h 内 url_check_status IS NULL 的条目，
    执行 HEAD 请求验证，结果写入 crawl_url_checks。
    失败只 log.warning，不抛异常。
    """
    try:
        from backend.services.url_batch_check_service import UrlBatchCheckService

        service = UrlBatchCheckService()
        result = await service.run_check(since_minutes=1440, limit=200)
        if result["checked"] > 0:
            _logger.info(
                f"url_full_check_job: checked={result['checked']} "
                f"succeeded={result['succeeded']} failed={result['failed']}"
            )
    except Exception as e:
        _logger.warning(f"url_full_check_job: {e}")


async def alert_evaluator_job() -> None:
    """v1.7 Phase 5: 对新 hotspot 跑告警评估.

    60s 间隔: 复用 evaluate_hotspot 对近期未评估 hotspot 跑规则匹配.
    """
    try:
        from backend.repository.db import get_connection
        from backend.services.alert_service import evaluate_hotspot

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


async def auto_extract_alert_job() -> None:
    """v1.8 R3: auto_extract + alert_evaluator 合并为单个 60s job。

    两者节奏相同 (60s)、都扫近期 hotspots, 合并后顺序执行减少
    调度器唤醒次数 (各自内部自带异常隔离)。
    """
    await _jobs_pkg.auto_extract_job()
    await alert_evaluator_job()

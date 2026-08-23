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
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

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


def job_done_event(job_type: str, job_id: str, duration_ms: int, ok: bool) -> None:
    """v0.5 M2-Task5: job_done SSE 事件发布 (SPEC §6.2 契约:
    payload = {type, id, duration_ms, ok})。

    用 fire-and-forget 模式 (create_task), 不阻塞 job 主体。
    失败只 log.warning, 避免污染业务流。
    """
    try:
        from backend.api.events import publish_event
        loop = asyncio.get_event_loop()
        loop.create_task(
            publish_event("job_done", {
                "type": job_type,
                "id": job_id,
                "duration_ms": duration_ms,
                "ok": ok,
            })
        )
    except Exception as e:
        _logger.warning(f"job_done_event publish failed ({job_type}/{job_id}): {e}")


def instrument_job(job_type: str):
    """装饰器: 自动包 job 函数, 完成后推 job_done SSE。

    用法::

        @instrument_job("collect_all")
        async def collect_all_job() -> None: ...

    注意: APScheduler 直接调 job 函数, 装饰器必须在 schedule_jobs 之前完成。
    """
    def decorator(coro):
        async def wrapper(*args, **kwargs):
            started_at = time.time() if 'time' in dir() else 0
            import time as _time
            started_at = _time.time()
            job_id = f"{job_type}-{int(started_at)}"
            ok = False
            try:
                result = await coro(*args, **kwargs)
                ok = True
                return result
            except Exception as e:
                _logger.error(f"{job_type} crashed: {e}")
                raise
            finally:
                duration_ms = int((_time.time() - started_at) * 1000)
                job_done_event(job_type, job_id, duration_ms, ok)

        wrapper.__name__ = coro.__name__
        wrapper.__doc__ = coro.__doc__
        return wrapper

    return decorator


async def collect_all_job() -> None:
    """周期性执行完整采集 + post-ingest 链。

    v1.8 R3: trend_rebuild / fts_rebuild / security_enrichment /
    url_content_check / export_rebuild 从 5 个独立定时 job 收敛为采集
    尾部链式执行 — 这些都是「数据变更后才有意义」的重建/检查, 独立
    定时在无新数据时纯属空转。采集失败时跳过链 (数据未变)。
    """
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
        return
    # ---- post-ingest 链 (各 job 内部自带异常隔离, 不会中断彼此) ----
    await trend_rebuild_job()
    await fts_rebuild_job()
    await security_enrichment_job()
    await url_content_check_job()
    await export_rebuild_job()
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


async def sm2_daily_push_job() -> None:
    """复利驱动器②: 每天 08:00 推送待复习条目到前端通知栏 (SSE review_due)。"""
    try:
        from backend.api.events import publish_event
        from backend.services.review_service import list_due

        due = list_due(limit=20)
        if not due:
            _logger.info("sm2_daily_push: no due items today")
            return

        await publish_event("review_due", {
            "count": len(due),
            "items": [{"id": d["entity_id"], "title": d.get("title", "")} for d in due],
        })
        _logger.info(f"sm2_daily_push: {len(due)} items pushed")
    except Exception as e:
        _logger.error(f"sm2_daily_push crashed: {e}")


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
    P0 修复: detect_stale_items 带每日配额 (STALE_ITEM_DAILY_QUOTA=50,
    按 updated_at 最旧优先), create_compile_task 对 pending 队列去重,
    避免历史积压 (1980+ 任务) 一次性全量入队。
    失败只 log.error，不抛异常。
    """
    try:
        from backend.services.compiler import (
            STALE_ITEM_DAILY_QUOTA,
            create_compile_task,
            detect_stale_items,
        )

        result = await asyncio.to_thread(detect_stale_items, STALE_ITEM_DAILY_QUOTA)
        stale_items = result.get("stale_items", [])
        if stale_items:
            compile_result = await asyncio.to_thread(create_compile_task, stale_items)
            skipped = compile_result.get("skipped_duplicates", 0)
            if compile_result.get("status") == "no_items":
                # 去重后无可创建条目 (全部已在 pending 队列中)
                _logger.info(
                    f"scheduled_compile_job: stale={len(stale_items)} "
                    f"created=0 skipped_duplicates={skipped}"
                )
            else:
                # 兼容两种返回形态: 单任务 {task_id} / 多任务 {tasks: [...]}
                created = compile_result.get("tasks") or [
                    {"task_id": compile_result.get("task_id")}
                ]
                _logger.info(
                    f"scheduled_compile_job: stale={len(stale_items)} "
                    f"created={len(created)} skipped_duplicates={skipped}"
                )
        else:
            _logger.info("scheduled_compile_job: no stale items")
    except Exception as e:
        _logger.error(f"scheduled_compile_job crashed: {e}")


async def consume_compile_tasks_job() -> None:
    """P0 消费策略: 自动消费者 — 批量执行 pending compile 任务 (规则式编译)。

    每日 02:30 (Asia/Shanghai) 在 scheduled_compile_job (02:00) 之后运行,
    两步:
      1. consume_compile_tasks: 按 item 配额 (CONSUME_DAILY_QUOTA=100)
         批量执行 pending compile 任务 — 分类 (auto_classifier) + 概念关联
         (concept_linker) + lifecycle 流转 (kl:link→kl:structure /
         legacy→generate) + md 回写 + done 文件 + _MAP 更新。
      2. archive_stale_compile_tasks: 归档超过 ARCHIVE_MAX_AGE_DAYS 天仍
         pending 的 compile 任务 (标记 failed + 移入 failed/), 防止队列
         在消费者失速时再次只增不减。
    失败只 log.error，不抛异常 (与既有 job 模式一致)。
    """
    try:
        from backend.services.compiler import (
            ARCHIVE_MAX_AGE_DAYS,
            CONSUME_DAILY_QUOTA,
            archive_stale_compile_tasks,
            consume_compile_tasks,
        )

        consumed = await asyncio.to_thread(
            consume_compile_tasks, CONSUME_DAILY_QUOTA
        )
        archived = await asyncio.to_thread(
            archive_stale_compile_tasks, ARCHIVE_MAX_AGE_DAYS
        )
        _logger.info(
            f"consume_compile_tasks_job: processed_tasks="
            f"{consumed.get('processed_tasks', 0)} "
            f"items={consumed.get('items_consumed', 0)} "
            f"archived={archived.get('archived', 0)}"
        )
    except Exception as e:
        _logger.error(f"consume_compile_tasks_job crashed: {e}")


async def scheduled_soul_job() -> None:
    """Phase 1f Task 6.8: 定时检查 SOUL.md 周期（>7天未更新则触发重新生成）。

    每周日 04:00 (Asia/Shanghai) 触发。
    失败只 log.error，不抛异常。
    """
    try:
        from datetime import datetime, timedelta, timezone

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


async def weekly_maintenance_job() -> None:
    """v1.8 R3: 周日维护链 — SOUL 重生成 → 掌握度迁移 → 周回顾 → db_diet。

    原 soul_weekly (Sun 04:00) / migrate_weekly (Sun 05:00) /
    summary_weekly (Sun 06:00) 三个 cron job 合并为单 job 顺序执行,
    保持原链式语义 (每个子 job 自带异常隔离, 不会中断后续)。

    v0.5 M2-Task4: 末尾追加 db_diet_job — 按 retention.json 台账清表,
    DB 瘦身的统一入口 (替代人工跑 scripts/db_diet.py)。
    """
    await scheduled_soul_job()
    await scheduled_migrate_job()
    await scheduled_summary_job()
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
        proc = subprocess.run(
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


async def quality_logs_cleanup_job() -> None:
    """P0.1: 归档超过保留窗口的 quality_check_logs。

    v0.5 §18: 已并入 telemetry_window_job (7 天遥测窗口统一入口),
    本函数保留为薄包装以维持向后兼容 (scheduler 不再单独注册)。
    """
    try:
        from backend.services.maintenance_service import cleanup_quality_logs

        result = await asyncio.to_thread(
            cleanup_quality_logs, days=7, dry_run=False
        )
        _logger.info(
            f"quality_logs_cleanup_job: retention_days=7 "
            f"archived={result.get('rows_archived')} "
            f"remaining={result.get('rows_remaining_after')}"
        )
    except Exception as e:
        _logger.error(f"quality_logs_cleanup_job crashed: {e}")


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
    "cg_event_process_job",
    "cg_service_scan_job",
    "cg_upstream_sync_job",
    "collect_all_job",
    "consume_compile_tasks_job",
    "daily_db_backup_job",  # P1: 每日数据库自动备份
    "daily_snapshot_job",
    "export_rebuild_job",
    "mitre_sync_job",
    "quality_logs_cleanup_job",  # P0: qcl 清理 (v0.5 起由 telemetry_window_job 承载)
    "telemetry_window_job",  # v0.5 §18: 7 天遥测窗口
    "reset_service",
    "scheduled_compile_job",
    "scheduled_migrate_job",
    "scheduled_soul_job",
    "scheduled_stats_job",
    "scheduled_summary_job",
    "security_enrichment_job",
    "set_service",
    "should_run_catchup",
    "source_reputation_rebuild_job",
    "sync_job",
    "trend_rebuild_job",
    "url_content_check_job",
    "weekly_report_job",
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
    """Phase 3: 每 300s 扫描未 enrichment 的 knowledge items，异步 enrichment.

    不阻塞采集主路径，独立 job 运行。

    P0-6 (2026-08-15): 修复两处致命错误:
    1. SELECT 从 hotspots 查 cve_ids/attack_techniques/compliance_refs —
       这些列只存在于 knowledge_items, hotspots 无此列 → 每轮必抛
       "no such column" 崩溃。改为查询 knowledge_items。
    2. UPDATE 用字符串拼接 JSON (COALESCE || ',' || ?) — 产生非法 JSON。
       改为 json 模块安全合并 (去重追加)。

    v0.4.0 收尾 (2026-08-16):
    3. 去掉「近 24h」限制 — 历史条目 (含 CVE/ATT&CK 标题模式) 从未被富化,
       富化字段全 NULL, item_entities 无数据可桥接。改为持续回填 (最旧优先,
       已富化条目因字段非 NULL 自动排除)。
    4. 无实体的条目打标 cve_ids='[]' — 避免每轮重复扫描无匹配条目。
    5. 富化出的实体写入 item_entities 桥接表 (item ↔ security entity),
       security graph 与 knowledge 由此统一命名空间。
    """
    try:
        import json as _json

        from backend.domain.security_models import _now_iso
        from backend.repository.db import get_connection
        from backend.security.enricher import enrich_batch

        conn = get_connection()

        # v0.4.0 预回填: 已富化 (字段非空) 但无 item_entities 桥接的条目
        # (历史富化发生在桥接逻辑之前, 字段有数据但桥接表为空)
        try:
            backfilled = 0
            rows_with_ent = conn.execute(
                "SELECT id, cve_ids, attack_techniques, compliance_refs "
                "FROM knowledge_items "
                "WHERE (cve_ids IS NOT NULL AND cve_ids != '[]') "
                "   OR (attack_techniques IS NOT NULL AND attack_techniques != '[]') "
                "   OR (compliance_refs IS NOT NULL AND compliance_refs != '[]')"
            ).fetchall()
            for r in rows_with_ent:
                exists = conn.execute(
                    "SELECT 1 FROM item_entities WHERE item_id = ? LIMIT 1", (r["id"],)
                ).fetchone()
                if exists:
                    continue
                for field, etype in (
                    ("cve_ids", "cve"),
                    ("attack_techniques", "attack_technique"),
                    ("compliance_refs", "compliance"),
                ):
                    val = r[field]
                    if not val:
                        continue
                    try:
                        for v in _json.loads(val):
                            conn.execute(
                                "INSERT OR IGNORE INTO item_entities "
                                "(item_id, entity_name, entity_type, confidence, source, created_at) "
                                "VALUES (?, ?, ?, 0.5, 'rule', ?)",
                                (r["id"], str(v), etype, _now_iso()),
                            )
                            backfilled += 1
                    except (ValueError, TypeError):
                        pass
            if backfilled:
                _logger.info(f"security_enrichment_job: backfilled {backfilled} item_entities")
        except Exception as e:
            _logger.warning(f"item_entities backfill failed: {e}")

        # 未富化条目 (不限时间; 优先含 CVE/ATT&CK/合规模式的标题 — 富化价值
        # 高, 避免先被无实体空壳条目占满批次; 富化后字段非 NULL 自动排除)
        # (knowledge_items 无 summary 列 — 正文在 .md 文件; 富化文本用
        # title + tags 拼接, enricher 的 CVE/ATT&CK/合规正则主要匹配标题)
        rows = conn.execute(
            "SELECT id, title, tags FROM knowledge_items "
            "WHERE (cve_ids IS NULL AND attack_techniques IS NULL AND compliance_refs IS NULL) "
            "ORDER BY "
            "  (title LIKE '%CVE%' OR title LIKE '%漏洞%' OR title LIKE '%ATT%CK%' "
            "   OR title LIKE '%攻击%' OR title LIKE '%安全%' OR title LIKE '%风险%') DESC, "
            "  ingested_at ASC LIMIT 200"
        ).fetchall()
        if not rows:
            return

        items = []
        for r in rows:
            item = {"id": r["id"], "title": r["title"] or ""}
            tags = r["tags"] or ""
            if tags:
                item["summary"] = " ".join(tags) if isinstance(tags, str) else " ".join(tags)
            items.append(item)
        enriched = enrich_batch(items)
        if not enriched:
            # v0.4.0: 无匹配 → 给本批条目打标, 防重复扫描
            now0 = _now_iso()
            for r in rows:
                try:
                    conn.execute(
                        "UPDATE knowledge_items SET cve_ids = '[]', updated_at = ? WHERE id = ?",
                        (now0, r["id"]),
                    )
                except Exception:
                    pass
            conn.commit()
            _logger.info(
                f"security_enrichment_job: {len(rows)} items no entities, marked done"
            )
            return

        now = _now_iso()
        count = 0
        for e in enriched:
            eid = e.get("id")
            if not eid:
                continue
            try:
                row = conn.execute(
                    "SELECT cve_ids, attack_techniques, compliance_refs "
                    "FROM knowledge_items WHERE id = ?",
                    (eid,),
                ).fetchone()
                if row is None:
                    continue

                def _merge_json(existing: str | None, new_val: str | None) -> str | None:
                    """合并 JSON 数组字段 (去重, 保持顺序)。"""
                    merged: list = []
                    if existing:
                        try:
                            merged.extend(_json.loads(existing))
                        except (ValueError, TypeError):
                            pass
                    if new_val:
                        try:
                            merged.extend(_json.loads(new_val))
                        except (ValueError, TypeError):
                            pass
                    # 去重且保留顺序
                    seen = set()
                    deduped = []
                    for v in merged:
                        if v not in seen:
                            seen.add(v)
                            deduped.append(v)
                    return _json.dumps(deduped, ensure_ascii=False) if deduped else None

                updates = {}
                entity_rows: list[tuple[str, str, float]] = []
                for field, etype in (
                    ("cve_ids", "cve"),
                    ("attack_techniques", "attack_technique"),
                    ("compliance_refs", "compliance"),
                ):
                    merged = _merge_json(row[field], e.get(field))
                    if merged:
                        updates[field] = merged
                        try:
                            for v in _json.loads(merged):
                                entity_rows.append((str(v), etype, 0.5))
                        except (ValueError, TypeError):
                            pass
                if updates:
                    updates["updated_at"] = now
                    set_sql = ", ".join(f"{f} = ?" for f in updates)
                    conn.execute(
                        f"UPDATE knowledge_items SET {set_sql} WHERE id = ?",
                        (*updates.values(), eid),
                    )
                    count += 1

                # v0.4.0 收尾: 写入 item_entities 桥接表 (item → security entity)
                # 此前 item_entities 全库无写入方 (0 行), security graph 与
                # knowledge 完全隔离。enrichment 出的 CVE/ATT&CK/合规实体
                # 在此落桥接, 供图谱/查询/实体统一命名空间使用。
                # (注意: item_entities.source 有 CHECK 约束 ('rule','agent','manual'))
                if entity_rows:
                    for name, etype, conf in entity_rows:
                        conn.execute(
                            "INSERT OR IGNORE INTO item_entities "
                            "(item_id, entity_name, entity_type, confidence, source, created_at) "
                            "VALUES (?, ?, ?, ?, 'rule', ?)",
                            (eid, name, etype, conf, now),
                        )
            except Exception as item_err:
                _logger.warning(f"security_enrichment_job item {eid} failed: {item_err}")

        conn.commit()
        _logger.info(f"security_enrichment_job: processed {len(rows)} items, enriched {count}")
    except Exception as e:
        _logger.error(f"security_enrichment_job crashed: {e}")


# ============================================================================
# v1.7 Phase 5: Agent 集成与双向环 — 10 个新 job
# ============================================================================

async def auto_extract_job() -> None:
    """v1.7 Phase 5: 同步执行 (无 Agent 时) 的简单标签提取.

    60s 间隔: 对未提取的 hotspot 调 extract_tags, 写入 tags + hotspot_tags.
    作为 agent_task_consumer_job 的同步回退路径.
    """
    try:
        from backend.repository.db import get_connection
        from backend.repository.tags_repo import TagRepository
        from backend.services.extract_service import extract_tags

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
    await auto_extract_job()
    await alert_evaluator_job()


# v1.8: review_scheduler_job / profile_updater_job (NoOp 占位) 已删除
# 复习由前端 /api/reviews/due 实时驱动, profile 信号由事件触发 apply_signal


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


# v1.8: kv_cache_cleanup_job (NoOp 占位) 已删除 —— kv_cache_service 于
# Phase 7 移除, 调度器早已不再注册该 job


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


# ============================================================================
# Phase 3: 源级调度 (每 60s)
# ============================================================================
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
            _svc.attach_collection_service(_service)  # _service 是模块级全局
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


# ============================================================================
# Phase 3: 死源探活 (每日 03:30 Asia/Shanghai)
# ============================================================================
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


# ============================================================================
# Phase 3: 源级告警评估 (每 300s)
# ============================================================================
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


# 更新 __all__
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


# ============================================================================
# v1.8 Phase 8: Watchdog — 检测孤儿 collection_runs + 自动追抓
# ============================================================================
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
    from datetime import datetime, timedelta, timezone

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


# ============================================================================
# v1.8 Phase 10: KL 状态机触发器 (T1 + T2 + 死信监控)
# ============================================================================
async def kl_trigger_t1_job() -> None:
    """Phase 10: 每 60s 跑一次 T1 (kl:raw → kl:refine).

    失败只 log.error, 不抛异常 (与既有 job 模式一致).
    """
    from backend.services.triggers.t1_raw_to_refine import T1Trigger
    try:
        t1 = T1Trigger()
        report = await asyncio.to_thread(t1.run_once)
        logger.info(
            f"kl_trigger_t1_job: candidates={report['candidates']} "
            f"advanced={report['advanced']} "
            f"skipped_duplicate={report['skipped_duplicate']} "
            f"failed={report['failed']}"
        )
    except Exception as e:
        logger.error(f"kl_trigger_t1_job crashed: {e}")


async def kl_trigger_t2_job() -> None:
    """Phase 10: 每 120s 跑一次 T2 (kl:refine → kl:link).

    失败只 log.error, 不抛异常.
    """
    from backend.services.triggers.t2_refine_to_link import T2Trigger
    try:
        t2 = T2Trigger()
        report = await asyncio.to_thread(t2.run_once)
        logger.info(
            f"kl_trigger_t2_job: candidates={report['candidates']} "
            f"advanced={report['advanced']} "
            f"low_link={report['low_link']} "
            f"failed={report['failed']}"
        )
    except Exception as e:
        logger.error(f"kl_trigger_t2_job crashed: {e}")


async def kl_dead_letter_retry_job() -> None:
    """Phase 10: 每 10min 监控死信队列.

    当前阶段仅做阈值告警: 活跃死信 > 50 条时记 warn (供运维巡检).
    真正的重试/重跑逻辑在 Phase 12 引入 (与 T3-T5 一起设计).
    """
    from backend.repository.kl_dead_letter_repo import KLDeadLetterRepository
    try:
        repo = KLDeadLetterRepository()
        # 同步 DB 操作放 thread pool
        counts = await asyncio.to_thread(
            lambda: {
                t: repo.list_active_count(trigger_name=t)
                for t in ("t1", "t2")
            }
        )
        total = sum(counts.values())
        if total > 50:
            logger.warning(
                f"kl_dead_letter_retry_job: {total} active dead letters "
                f"(per-trigger: {counts}) — manual review recommended"
            )
        else:
            logger.debug(
                f"kl_dead_letter_retry_job: {total} active dead letters"
            )
    except Exception as e:
        logger.error(f"kl_dead_letter_retry_job crashed: {e}")


async def kl_trigger_t3_job() -> None:
    """Phase 12: 每 600s 跑一次 T3 (kl:link → kl:structure)."""
    from backend.services.triggers.t3_link_to_structure import T3Trigger
    try:
        t3 = T3Trigger()
        report = await asyncio.to_thread(t3.run_once)
        logger.info(
            f"kl_trigger_t3_job: candidates={report['candidates']} "
            f"advanced={report['advanced']} "
            f"low_link={report['low_link']} "
            f"failed={report['failed']}"
        )
    except Exception as e:
        logger.error(f"kl_trigger_t3_job crashed: {e}")


async def kl_trigger_t4_job() -> None:
    """Phase 12: 每 1800s 跑一次 T4 (kl:structure → kl:publish)."""
    from backend.services.triggers.t4_structure_to_publish import T4Trigger
    try:
        t4 = T4Trigger()
        report = await asyncio.to_thread(t4.run_once)
        logger.info(
            f"kl_trigger_t4_job: candidates={report['candidates']} "
            f"advanced={report['advanced']} "
            f"skipped_low_score={report['skipped_low_score']} "
            f"skipped_unstable={report['skipped_unstable']} "
            f"failed={report['failed']}"
        )
    except Exception as e:
        logger.error(f"kl_trigger_t4_job crashed: {e}")


# ============================================================================
# Phase 13: job 36 — 规划动作检查 (每 600s)
# ============================================================================
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


# ============================================================================
# Phase 14: job 38 — 技术栈漂移评估 (每小时)
# ============================================================================
async def cg_drift_assess_job() -> None:
    """Phase 14: 每小时评估一次 tech_stack drift."""
    try:
        from backend.services.codegarden_drift import assess_drift
        report = await asyncio.to_thread(assess_drift)
        logger.info(
            f"cg_drift_assess_job: {report['matched_count']} new assessments, "
            f"{len(report['new_techs'])} techs, "
            f"{len(report['affected_projects'])} projects"
        )
    except Exception as e:
        logger.error(f"cg_drift_assess_job crashed: {e}")


# ============================================================================
# Phase 14: job 39 — CVE 同步 (每 30 分钟)
# ============================================================================
async def cve_sync_to_security_job() -> None:
    """Phase 14: 每 30 分钟同步 CVE 到 security_entities."""
    try:
        from backend.services.cve_knowledge_sync import sync_cve_to_security
        report = await asyncio.to_thread(sync_cve_to_security)
        logger.info(
            f"cve_sync_to_security_job: synced={report['synced']} "
            f"updated={report['updated']} failed={report['failed']}"
        )
    except Exception as e:
        logger.error(f"cve_sync_to_security_job crashed: {e}")


# ============================================================================
# Phase 17: job — attention 聚合 (每 30 分钟)
# ============================================================================
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


# ============================================================================
# Phase 1.4 (Crawler v2): 标讯过期检查 (每 30 分钟)
# ============================================================================
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


# ============================================================================
# Phase 2.2 (Crawler v2): URL 全量校验 (每 5 分钟)
# ============================================================================
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


# ============================================================================
# P1-5: 知识分类消费提速 — 未分类条目批量规则分类 (每 30 分钟)
# ============================================================================
async def knowledge_classify_job() -> None:
    """P1-5: 批量规则分类未分类知识条目 (domain/type 为 null 的)。

    背景: 81-94% 条目的 domain/topic/type/difficulty 为 null — 分类只靠
    手动 API + 每日 02:30 编译消费者 (配额 100/天), 消费速率远低于摄入。
    新增独立 job: 每 30min 处理最多 500 条未分类条目 (纯规则, 无 LLM/网络),
    P0.4: 只更新 DB, 不回写 md (分类是中间状态, md 只由用户/编译器写)。
    """
    from datetime import datetime, timezone

    from backend.repository.db import get_connection
    from backend.repository.knowledge_repo import knowledge_repo
    from backend.services.auto_classifier import batch_classify

    _CLASSIFY_BATCH = 500
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, tags, source_url, domain, type, difficulty "
        "FROM knowledge_items "
        "WHERE domain IS NULL OR type IS NULL OR difficulty IS NULL "
        "ORDER BY ingested_at ASC LIMIT ?",
        (_CLASSIFY_BATCH,),
    ).fetchall()
    if not rows:
        return

    items = [dict(r) for r in rows]
    classified = batch_classify(items)
    updated = 0
    errors = 0
    now = datetime.now(timezone.utc).isoformat()
    for d in classified:
        item_id = d.get("id")
        if not item_id:
            continue
        try:
            db_item = knowledge_repo.get_item(item_id)
            if db_item is None:
                continue
            changed = False
            if d.get("domain") and not db_item.domain:
                db_item.domain = d["domain"]
                changed = True
            if d.get("type") and not db_item.type:
                db_item.type = d["type"]
                changed = True
            if d.get("difficulty") and not db_item.difficulty:
                db_item.difficulty = d["difficulty"]
                changed = True
            if d.get("topic") and not db_item.topic:
                db_item.topic = d["topic"]
                changed = True
            if not changed:
                continue
            db_item.updated_at = now
            # P0.4: 只更新 DB, 不回写 md (分类是中间状态)
            knowledge_repo.upsert_item(db_item)
            updated += 1
        except Exception as e:
            errors += 1
            _logger.warning(f"knowledge_classify item {item_id} failed: {e}")
    _logger.info(
        f"knowledge_classify_job: scanned={len(rows)} updated={updated} errors={errors}"
    )


# ============================================================================
# P3-4: 内容链路最小闭环 — kl:publish / 高注意力条目 → 内容草稿 (每 6 小时)
# ============================================================================
async def content_draft_generation_job() -> None:
    """P3-4: 从已发布/高注意力知识条目生成内容草稿, 打通"知识→内容"闭环。

    背景: content_calendar=0、drafts=1 — 内容日历/草稿层无自动输入。
    本 job: 选 kl:publish 条目 + kl:structure 且 attention_score 较高的
    条目, 若尚无对应草稿则用条目正文 (knowledge/items/{id}.md) 生成草稿。
    """
    try:
        from datetime import datetime, timezone

        from backend.repository.db import get_connection
        from backend.repository.knowledge_repo import knowledge_repo
        from backend.services.content_service import create_draft
        from backend.services.knowledge_sync import ITEMS_DIR

        _DRAFT_BATCH = 10
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title FROM knowledge_items "
            "WHERE lifecycle = 'kl:publish' "
            "   OR (lifecycle = 'kl:structure' AND COALESCE(attention_score, 0) >= 20) "
            "ORDER BY COALESCE(attention_score, 0) DESC, ingested_at DESC "
            "LIMIT ?",
            (_DRAFT_BATCH,),
        ).fetchall()
        if not rows:
            return

        # 已存在草稿的 title 集合 (避免重复生成)
        existing_drafts = {
            (d.get("title") or "").strip() for d in knowledge_repo.list_drafts()
        }
        created = 0
        for r in rows:
            title = (r["title"] or "").strip()
            if not title or title in existing_drafts:
                continue
            # 从条目 .md 读正文
            body = ""
            md_path = ITEMS_DIR / f"{r['id']}.md"
            try:
                if md_path.exists():
                    import re as _re
                    text = md_path.read_text(encoding="utf-8")
                    m = _re.match(r"^---\s*\n.*?\n---\s*\n", text, _re.DOTALL)
                    if m:
                        body = text[m.end():]
            except Exception:
                body = ""
            try:
                draft = create_draft(title=title, content=body or f"# {title}\n")
                existing_drafts.add(title)
                created += 1
                # P3-4 补充: 草稿自动排期到内容日历 (7 天后, 避免与既有条目撞期)
                try:
                    from datetime import timedelta as _td

                    from backend.services.content_service import create_calendar_entry
                    sched_date = (
                        datetime.now(timezone.utc) + _td(days=7)
                    ).strftime("%Y-%m-%d")
                    create_calendar_entry(
                        date=sched_date,
                        topic=title[:80],
                        type="article",
                        source_items=[r["id"]],
                    )
                except Exception as cal_err:
                    _logger.warning(f"content calendar schedule failed for {r['id']}: {cal_err}")
            except Exception as e:
                _logger.warning(f"content draft create failed for {r['id']}: {e}")
        _logger.info(
            f"content_draft_generation_job: candidates={len(rows)} created={created}"
        )
    except Exception as e:
        _logger.error(f"content_draft_generation_job crashed: {e}")


# ============================================================================
# 遗留项: 知识库 URL 空壳条目内容补全 (每 6 小时, 20 条/批)
# ============================================================================
async def knowledge_stub_backfill_job() -> None:
    """补全知识库空壳条目 — title 为 URL 或正文过短的条目, 抓取原文提取标题+摘要。

    背景: bookmark 批量导入产生大量无标题/无正文条目 (title=URL,
    body<40 字符), 知识库"信息进入"层质量差。本 job 尽力而为:
    每 6h 处理 20 条, 并发 3, 抓取失败跳过 (下轮重试), 不阻塞主流程。
    """
    try:
        import asyncio as _asyncio
        import re as _re
        from datetime import datetime, timezone

        from backend.repository.db import get_connection
        from backend.repository.knowledge_repo import knowledge_repo
        from backend.services import ai_hub
        from backend.services.knowledge_sync import ITEMS_DIR

        _BATCH = 20
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, title, source_url FROM knowledge_items "
            "WHERE (title LIKE 'http%' OR title = 'Untitled' OR title = '') "
            "   AND source_url IS NOT NULL AND source_url != '' "
            "ORDER BY ingested_at ASC LIMIT ?",
            (_BATCH,),
        ).fetchall()
        if not rows:
            return

        async def _fetch_one(r) -> tuple[str, str, str] | None:
            """抓取 URL, 返回 (item_id, real_title, snippet)."""
            item_id, old_title, url = r["id"], r["title"], r["source_url"]
            try:
                from backend.collectors.session import BackendSession
                timeout = 12
                async with BackendSession(timeout=timeout) as session:
                    resp = await session.get(url, timeout=timeout)
                    if resp.status != 200:
                        return None
                    html = await resp.text(encoding="utf-8", errors="replace")
                m = _re.search(r"<title[^>]*>(.*?)</title>", html, _re.IGNORECASE | _re.DOTALL)
                real_title = ""
                if m:
                    real_title = _re.sub(r"\s+", " ", m.group(1)).strip()[:200]
                # 摘要: meta description
                desc = ""
                dm = _re.search(
                    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
                    html, _re.IGNORECASE,
                )
                if not dm:
                    dm = _re.search(
                        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
                        html, _re.IGNORECASE,
                    )
                if dm:
                    desc = _re.sub(r"\s+", " ", dm.group(1)).strip()[:500]
                return item_id, real_title or old_title, desc
            except Exception:
                return None

        sem = _asyncio.Semaphore(3)

        async def _limited(r):
            async with sem:
                return await _fetch_one(r)

        results = await _asyncio.gather(*[_limited(r) for r in rows])
        updated = 0
        for res in results:
            if not res:
                continue
            item_id, real_title, snippet = res
            try:
                db_item = knowledge_repo.get_item(item_id)
                if db_item is None:
                    continue
                changed = False
                if real_title and (not db_item.title or db_item.title.startswith("http")):
                    db_item.title = real_title
                    changed = True
                if snippet and not db_item.topic:
                    db_item.topic = snippet[:100]
                    changed = True
                if changed:
                    db_item.updated_at = datetime.now(timezone.utc).isoformat()
                    # 同时回写 .md 正文 (把摘要作为正文骨架)
                    md_path = ITEMS_DIR / f"{item_id}.md"
                    try:
                        if md_path.exists():
                            text = md_path.read_text(encoding="utf-8")
                            m = _re.match(r"^---\s*\n.*?\n---\s*\n", text, _re.DOTALL)
                            body = text[m.end():].strip() if m else text.strip()
                            if len(body) < 40:
                                ai_hub.write_item(
                                    db_item.to_dict(),
                                    content=(f"# {real_title}\n\n{snippet}\n" if snippet else None),
                                    agent="job:stub_backfill",
                                )
                                changed = True
                    except Exception as md_err:
                        _logger.warning(f"stub backfill md write failed {item_id}: {md_err}")
                    knowledge_repo.upsert_item(db_item)
                    updated += 1
            except Exception as e:
                _logger.warning(f"stub backfill item {item_id} failed: {e}")
        _logger.info(
            f"knowledge_stub_backfill_job: candidates={len(rows)} updated={updated}"
        )
    except Exception as e:
        _logger.error(f"knowledge_stub_backfill_job crashed: {e}")


# ============================================================================
# v0.4 收尾: knowledge_chunks 段落切分生成 (每 30 分钟, 200 条/批)
# ============================================================================
async def knowledge_chunk_generation_job() -> None:
    """为无 chunks 的知识条目生成段落 chunks (FTS5 触发器自动同步索引)。

    背景: knowledge_chunks 表自建表后 0 行 — 生成只靠手动 API, 全文检索
    (FTS5) 从未有数据。本 job 每 30min 处理 200 条无 chunks 条目。
    """
    try:
        from backend.repository.db import get_connection
        from backend.services.chunk_service import generate_chunks_for_item

        _BATCH = 200
        conn = get_connection()
        rows = conn.execute(
            "SELECT id FROM knowledge_items ki "
            "WHERE NOT EXISTS (SELECT 1 FROM knowledge_chunks c WHERE c.item_id = ki.id) "
            "ORDER BY ki.ingested_at ASC LIMIT ?",
            (_BATCH,),
        ).fetchall()
        if not rows:
            return

        created = 0
        skipped = 0
        for r in rows:
            result = await asyncio.to_thread(generate_chunks_for_item, r["id"])
            if result.get("created", 0) > 0:
                created += result["created"]
            else:
                skipped += 1
        _logger.info(
            f"knowledge_chunk_generation_job: candidates={len(rows)} "
            f"created_chunks={created} skipped={skipped}"
        )
    except Exception as e:
        _logger.error(f"knowledge_chunk_generation_job crashed: {e}")


# ============================================================================
# v0.4 收尾: security ↔ knowledge 实体统一命名空间 (每 10 分钟)
# ============================================================================
async def security_entity_concept_sync_job() -> None:
    """统一 security_entities 与 knowledge_concepts 命名空间。

    PRD A.3.2 遗留: security 实体 (CVE/ATT&CK/合规) 与 knowledge concepts
    两套库完全隔离, 同一实体重复无互引。此前 item_entities 无写入方 (0 行)。

    v0.4.0 收尾, 本 job 三件事:
    1. item_entities 中的实体 → 确保 security_entities 存在
       (CVE 编号以 type='cve' 入库, name 为 CVE-ID, id 为实体名)
    2. 高频实体 (≥3 条引用) → 创建 knowledge concept, 通过 entity_type +
       external_id 指向 security_entity (两库互引)
    3. 幂等: 已存在的跳过
    """
    try:
        from backend.domain.security_models import _now_iso
        from backend.repository.db import get_connection
        from backend.repository.knowledge_repo import knowledge_repo

        conn = get_connection()
        now = _now_iso()

        # 1. item_entities → security_entities (按实体名/类型聚合)
        rows = conn.execute(
            "SELECT entity_name, entity_type, COUNT(*) AS cnt "
            "FROM item_entities GROUP BY entity_name, entity_type"
        ).fetchall()
        synced = 0
        for r in rows:
            name = r["entity_name"]
            etype = r["entity_type"]
            try:
                exists = conn.execute(
                    "SELECT 1 FROM security_entities WHERE name = ? AND entity_type = ? LIMIT 1",
                    (name, etype),
                ).fetchone()
                if not exists:
                    conn.execute(
                        "INSERT INTO security_entities "
                        "(id, entity_type, name, description, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (f"{etype}:{name}", etype, name, f"自动同步自知识库实体 ({etype})", now, now),
                    )
                    synced += 1
            except Exception as e:
                _logger.warning(f"security_entity sync {name} failed: {e}")

        # 2. 高频实体 → knowledge concept 互引 (≥3 条引用, 防概念污染)
        from backend.domain.knowledge_models import KnowledgeConcept
        concept_created = 0
        concept_linked = 0
        for r in rows:
            if r["cnt"] < 3:
                continue
            name = r["entity_name"]
            etype = r["entity_type"]
            slug = f"{etype}-{name}".lower().replace(":", "-").replace("/", "-")[:120]
            try:
                concept = knowledge_repo.get_concept(slug)
                if concept is None:
                    knowledge_repo.upsert_concept(KnowledgeConcept(
                        slug=slug,
                        title=name,
                        domain="security",
                        source_items=[],
                        updated_at=now,
                        entity_type=etype,
                        external_id=f"{etype}:{name}",
                        external_ref=f"security_entity:{etype}:{name}",
                    ))
                    concept_created += 1
                elif not concept.external_id:
                    concept.entity_type = etype
                    concept.external_id = f"{etype}:{name}"
                    concept.external_ref = f"security_entity:{etype}:{name}"
                    concept.updated_at = now
                    knowledge_repo.upsert_concept(concept)
                    concept_linked += 1
            except Exception as e:
                _logger.warning(f"concept link {name} failed: {e}")

        conn.commit()
        _logger.info(
            f"security_entity_concept_sync_job: entities={len(rows)} "
            f"synced={synced} concept_created={concept_created} concept_linked={concept_linked}"
        )
    except Exception as e:
        _logger.error(f"security_entity_concept_sync_job crashed: {e}")


# ============================================================================
# v0.5 M3.5 wiki_archiver: 30 天归档 (每日 03:50 Asia/Shanghai,
# 避开 03:00/03:30 profile_decay / source_probe 时段, 与 04:00 collect_validations 错开)
# ============================================================================
async def wiki_archiver_job() -> None:
    """每日扫描 SQLite 知识条目, 把 ingested_at < now-30d 且未收藏的条目
    原子写入 ``llm-wiki-2.0/items/{id}.md``, 同时建 sources/ 抓取快照 + retention 初始 entry。

    关闭策略: ``config.llm_wiki_v2=False`` 时直接跳过。
    """
    from backend.config import config

    if not config.llm_wiki_v2:
        _logger.info("wiki_archiver_job skipped (llm_wiki_v2 disabled)")
        return

    from backend.services.wiki_archiver import archive_overdue_items

    _t0 = datetime.now(tz=timezone.utc)
    try:
        stats = archive_overdue_items(
            wiki_root=config.llm_wiki_v2_path,
            days=30,
        )
        _logger.info(
            f"wiki_archiver_job: {stats} (wiki_root={config.llm_wiki_v2_path})"
        )
    except Exception as e:
        _logger.error(f"wiki_archiver_job crashed: {e}")
        try:
            job_done_event("wiki_archiver", "wiki_archiver", 0, ok=False)
        except Exception:
            pass
        return
    duration_ms = int((datetime.now(tz=timezone.utc) - _t0).total_seconds() * 1000)
    ok = stats.get("errors", 0) == 0
    try:
        job_done_event("wiki_archiver", "wiki_archiver", duration_ms, ok=ok)
    except Exception:
        pass


# ============================================================================
# v0.5 M3.5 retention_decay: Ebbinghaus 衰减 (每周日 05:30 Asia/Shanghai,
# 紧跟 05:00 telemetry_window)
# ============================================================================
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


# 更新 __all__ (Phase 1.4 + Phase 2.2 + existing)
__all__.extend([
    "attention_aggregate_job",
    "bid_expiry_check_job",
    "catchup_watchdog_job",
    "cg_drift_assess_job",
    "content_draft_generation_job",
    "cve_sync_to_security_job",
    "kl_dead_letter_retry_job",
    "kl_trigger_t1_job",
    "kl_trigger_t2_job",
    "kl_trigger_t3_job",
    "kl_trigger_t4_job",
    "knowledge_chunk_generation_job",
    "knowledge_classify_job",
    "knowledge_stub_backfill_job",
    "planning_action_check_job",
    "retention_decay_job",
    "security_entity_concept_sync_job",
    "url_full_check_job",
    "wiki_archiver_job",
])

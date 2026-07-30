"""v1.8 Phase 8 — 追抓资讯 (News Catchup) Service.

设计要点
--------
- **独立 asyncio.Lock** (``_lock``): 与 collect_all 互不阻塞, 可并行
- **状态机**: 一次只允许一个 manual catchup (返回 409), auto catchup
  可与 manual 并行 (优先级低, 让 manual 跑完再让出锁)
- **跳过 dead 源**: ``source_stats.status='dead' AND updated_at < now-24h``
  的源不进入本轮抓取
- **执行模型**: 复用 collection_service 的并发模型 (asyncio.gather per
  category), 但每分类下又分源级并发, 互不阻塞 collect_all
- **v1.9 Phase 9 — 标准化**: 每次 run 记录 per-source checkpoint
  (断点续传), 写结构化事件日志, 跑 4 类数据完整性验证

任务边界
--------
- B (Watchdog): 仅调用本模块的 ``enqueue_catchup`` 接口
- C (Service): 本文件实现主流程 ``run()`` + 选源 + 抓取 + 写库
- D (API): 通过 ``enqueue_catchup`` / ``abort_current`` 间接调用
"""
from __future__ import annotations

import asyncio
import json
import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.logging_config import logger as _root_logger
from backend.repository.catchup_checkpoint_repo import CatchupCheckpointRepository
from backend.repository.catchup_repo import CatchupRepository, CatchupStatus
from backend.services import collection_logger as _clog
from backend.services.collect_validator import validate_and_persist

# Module-level state (Phase 8 watchdog 需要)
logger = _root_logger.bind(component="catchup_service")
_repo = CatchupRepository()
_ckpt_repo = CatchupCheckpointRepository()

# 续传窗口: 24h 内同一 source 已 done → 本 run 跳过
_RESUMPTION_WINDOW_HOURS = 24

# Watchdog 写入, /api/health 读取
_last_orphan_recovery_at: Optional[str] = None
# Watchdog 防抖: 上次 enqueue_auto 的时间, 避免重复触发
_last_auto_enqueue_at: Optional[datetime] = None
_AUTO_ENQUEUE_DEBOUNCE_S = 300  # 5 分钟内不重复 enqueue auto

# 全局 lock (C 任务扩展为 CatchupService 类)
_lock = asyncio.Lock()
_current_manual_run: Optional[int] = None


def get_last_orphan_recovery_at() -> Optional[str]:
    """/api/health 读取这个值"""
    return _last_orphan_recovery_at


def set_last_orphan_recovery_at(iso_ts: str) -> None:
    """watchdog 标记最近一次孤儿恢复时间 (供 /api/health 暴露)"""
    global _last_orphan_recovery_at
    _last_orphan_recovery_at = iso_ts


def get_current_manual_run_id() -> Optional[int]:
    """API 端点查询当前 manual run id (用于 abort)"""
    return _current_manual_run


# ---------------------------------------------------------------------------
# Public enqueue 接口 (B 任务用, C/D 任务也用)
# ---------------------------------------------------------------------------
async def enqueue_catchup(
    *,
    mode: str,
    since: str,
    until: Optional[str],
    categories: Optional[list[str]] = None,
    max_per_source: int = 20,
    force: bool = False,
) -> int:
    """Enqueue a new catchup run.

    立即返回 run_id (不阻塞), 后台 fire-and-forget 实际执行.

    Parameters
    ----------
    mode : "auto" | "manual"
        "manual" 检查当前是否有 manual 跑, 有则抛 HTTPException(409).
        "auto" 不阻塞, 跳过防抖检查.
    since : ISO 8601 UTC
        追抓窗口起点.
    until : ISO 8601 UTC, optional
        追抓窗口终点. None = now.
    categories : list[str], optional
        要追抓的分类. None = all.
    max_per_source : int
        单源最大抓取数 (节流).
    force : bool, default False
        P0-3: 跳过 24h 续传窗口检查, 即使该源在最近 24h 已 done
        也会重新跑. 用于源失效后强制重抓.

    Returns
    -------
    int
        新建的 catchup_runs.id.

    Raises
    ------
    ValueError
        mode 非法 / 参数非法.
    """
    if mode not in ("auto", "manual"):
        raise ValueError(f"invalid mode: {mode}")
    if max_per_source <= 0 or max_per_source > 200:
        raise ValueError(f"max_per_source out of range: {max_per_source}")

    # manual 模式: 检查并发 + 占位
    if mode == "manual":
        global _current_manual_run
        if _lock.locked() and _current_manual_run is not None:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"A manual catchup is already running (run_id={_current_manual_run})",
                    "active_run_id": _current_manual_run,
                },
            )
        # 占位 (执行函数会重置)
        _current_manual_run = -1  # 临时, 真实 id 会在 _execute 中填入

    # 创建 row
    run = _repo.create(
        mode=mode,
        since_window=since,
        until_window=until,
        categories=json.loads(json.dumps(categories or [])),  # deep copy
        max_per_source=max_per_source,
    )

    if mode == "manual":
        _current_manual_run = run.id

    logger.info(
        f"enqueue_catchup: run_id={run.id} mode={mode} "
        f"since={since} until={until} categories={categories} "
        f"max_per_source={max_per_source} force={force}"
    )

    # Fire-and-forget 后台执行
    asyncio.create_task(_execute_catchup_run(run.id, mode=mode, force=force))
    return run.id


async def abort_current() -> Optional[int]:
    """Abort 当前 manual run. Returns 被中止的 run_id 或 None.

    Phase 8 B stub: 直接调 repo.abort() 改 DB 状态. C 任务可加入
    协作式 CancelledError 通知.
    """
    global _current_manual_run
    if _current_manual_run is None:
        return None
    run_id = _current_manual_run
    if _repo.abort(run_id):
        logger.info(f"abort_current: run_id={run_id} marked aborted")
        _current_manual_run = None
        return run_id
    return None


# ---------------------------------------------------------------------------
# Internal: 实际执行 (C 任务实现)
# ---------------------------------------------------------------------------
def _get_dead_source_names(cutoff_hours: int = 24) -> dict[str, set[str]]:
    """读 source_stats, 返回 {category: {source_name, ...}} 的 dead 源集合.

    dead 判定: status='dead' AND last_checked_at < now - cutoff_hours.
    这样刚被 watchdog 标死的源 (新死) 还会被尝试一次, 减少误杀.
    """
    try:
        from datetime import timedelta
        from backend.repository.db import get_connection
        from backend.repository.source_stats_repo import SourceStatsRepository

        repo = SourceStatsRepository()
        rows = repo.list_all()  # list of dicts
        cutoff_iso = (
            datetime.now(timezone.utc) - timedelta(hours=cutoff_hours)
        ).isoformat()
        dead: dict[str, set[str]] = {}
        for r in rows:
            if r.get("status") != "dead":
                continue
            last_checked = r.get("last_checked_at")
            if not last_checked or last_checked > cutoff_iso:
                continue
            cat = r.get("category")
            name = r.get("source_name")
            if cat and name:
                dead.setdefault(cat, set()).add(name)
        return dead
    except Exception as e:
        logger.warning(f"_get_dead_source_names failed: {e}")
        return {}


async def _execute_catchup_run(run_id: int, *, mode: str, force: bool = False) -> None:
    """C 任务: 实际追抓主流程.

    流程
    ----
    1. 读 run 配置 (categories / max_per_source)
    2. 选源: 跳过 ``source_stats.status='dead' AND last_checked_at < now-24h``
    3. 临时修改每个 collector.sources (过滤 dead) + max_items (cap)
    4. v1.9 续传: 同一 (cat, source) 在最近 24h 已 done → pre-mark skipped
       (P0-3: force=True 时跳过此检查)
    5. 复用 CollectionService.run_once() 跑并发抓取
    6. v1.9 per-source checkpoint: 写 catchup_checkpoints (done/failed)
    7. v1.9 结构化日志: source_done / source_failed / collect_done
    8. write progress (持续更新 ingested / succeeded)
    9. 触发 trend_rebuild_job (后台)
    10. v1.9 跑 4 类数据完整性验证 (source_regression / time_gap /
        category_anomaly / cross_source) — 写 collect_validations
    11. finish: success (有 item) / partial (部分源失败) / failed (整轮炸)

    异常隔离: 单 collector crash 不影响其他;整体 catchup 崩了会标 failed.
    """
    global _current_manual_run
    from backend.repository.hotspot_repo import HotspotRepository
    from backend.domain.enums import Category

    run = _repo.get(run_id)
    if run is None:
        logger.error(f"_execute_catchup_run: run_id={run_id} not found")
        if mode == "manual":
            _current_manual_run = None
        return

    items_ingested = 0
    sources_attempted = 0
    sources_succeeded = 0
    sources_skipped = 0
    sources_failed = 0
    original_sources: dict = {}
    original_max_items: dict = {}
    target_cats: list = []
    svc = None

    # v1.9: 时间窗口 (run.since_window 一定存在; until 可能为 None)
    since_iso = str(run.since_window) if run.since_window else ""
    until_iso = (
        str(run.until_window)
        if run.until_window
        else datetime.now(timezone.utc).isoformat()
    )

    try:
        # 1. 选源: 跳过 dead >= 24h
        dead_map = _get_dead_source_names(cutoff_hours=24)
        total_dead_skipped = sum(len(v) for v in dead_map.values())

        # 2. 决定跑哪些 category
        from backend.domain.enums import Category
        if run.categories:
            try:
                target_cats = [Category(c) for c in run.categories]
            except ValueError as e:
                logger.error(f"invalid categories in run {run_id}: {e}")
                _repo.finish(
                    run_id, status="failed", items_ingested=0, items_skipped=0,
                    sources_attempted=0, sources_succeeded=0,
                    error_msg=f"invalid categories: {e}",
                )
                if mode == "manual":
                    _current_manual_run = None
                return
        else:
            target_cats = list(Category)

        # 3. 实例化 + 过滤 + cap
        from backend.services.collection_service import CollectionService
        svc = CollectionService()
        # 保存原值, 跑完恢复 (避免影响后续 collect_all)
        for cat in target_cats:
            if cat not in svc.collectors:
                continue
            collector = svc.collectors[cat]
            original_sources[cat] = list(collector.sources)
            original_max_items[cat] = int(collector.max_items)
            # 过滤 dead 源
            dead_names = dead_map.get(cat.value, set())
            if dead_names:
                filtered = [s for s in collector.sources if s.get("name") not in dead_names]
                collector.sources = filtered
            # cap max_items
            collector.max_items = min(original_max_items[cat], int(run.max_per_source))

        sources_attempted = sum(
            len(svc.collectors[c].sources) for c in target_cats if c in svc.collectors
        )

        # 4. v1.9 续传: 同一 (cat, source) 最近 24h 已 done → 跳过
        # P0-3: force=True 时跳过续传检查, 强制重抓
        if force:
            logger.info(
                f"_execute_catchup_run: run_id={run_id} force=True, "
                f"skipping 24h resumption check"
            )
        try:
            cutoff_iso = (
                datetime.now(timezone.utc)
                - timedelta(hours=_RESUMPTION_WINDOW_HOURS)
            ).isoformat()
            for cat in target_cats:
                if cat not in svc.collectors:
                    continue
                for src in svc.collectors[cat].sources:
                    name = src.get("name", "")
                    if not name:
                        continue
                    # P0-3: force=True 时直接跳过续传查询
                    if force:
                        continue
                    recent = _ckpt_repo.list_recent_done(
                        cat.value, name, since_iso=cutoff_iso, limit=1
                    )
                    if recent:
                        try:
                            _ckpt_repo.mark_skipped(
                                run_id, cat.value, name,
                                reason="resumed from prior run",
                            )
                            _clog.log_collect_event(
                                "source_skipped",
                                run_id=run_id,
                                category=cat.value,
                                source=name,
                                checkpoint_status="skipped",
                                previous_finished_at=recent[0].finished_at,
                            )
                            sources_skipped += 1
                        except Exception as e:
                            logger.warning(
                                f"checkpoint mark_skipped failed: {cat.value}/{name}: {e}"
                            )
        except Exception as e:
            logger.warning(f"resumption check failed: {e}")

        # 真正需要执行的 source 数 (= attempted - skipped)
        effective_attempted = max(0, sources_attempted - sources_skipped)
        _repo.update_progress(
            run_id,
            sources_attempted=sources_attempted,
            items_skipped=sources_skipped,
        )
        logger.info(
            f"_execute_catchup_run: run_id={run_id} mode={mode} "
            f"categories={[c.value for c in target_cats]} "
            f"sources={sources_attempted} (skipped {sources_skipped} resumed, "
            f"{total_dead_skipped} dead) effective={effective_attempted} "
            f"max_per_source={run.max_per_source}"
        )

        # v1.9: collect_start 事件
        _clog.log_collect_event(
            "collect_start",
            run_id=run_id,
            mode=mode,
            since=since_iso,
            until=until_iso,
            max_per_source=int(run.max_per_source),
            sources_attempted=sources_attempted,
            sources_skipped=sources_skipped,
        )

        # 5. 跑 (用 single-category run_one 路径)
        for cat in target_cats:
            if cat not in svc.collectors:
                continue
            cat_start = _time.time()
            _clog.log_collect_event(
                "category_start",
                run_id=run_id,
                category=cat.value,
                n_sources=len(svc.collectors[cat].sources),
            )
            try:
                report = await svc.run_one(cat)
                cat_duration_ms = int((_time.time() - cat_start) * 1000)
                if report.results:
                    items_ingested += int(report.total)

                # v1.9: per-source checkpoint + 结构化日志
                try:
                    source_results = list(
                        getattr(svc.collectors[cat], "last_source_results", []) or []
                    )
                    cat_succeeded = 0
                    cat_failed = 0
                    for sr in source_results:
                        name = sr.source_name
                        if not name:
                            continue
                        # 续传 pre-mark 跳过的源: 不要再覆盖
                        existing = _ckpt_repo.get(run_id, cat.value, name)
                        if existing and existing.status == "skipped":
                            continue
                        count = int(sr.item_count or 0)
                        err = sr.error_msg
                        if err:
                            cat_failed += 1
                            try:
                                err_str = str(err) if not isinstance(err, BaseException) else f"{type(err).__name__}: {err}"
                                _ckpt_repo.mark_failed(
                                    run_id, cat.value, name, err_str,
                                )
                            except Exception as e:
                                logger.warning(
                                    f"checkpoint mark_failed failed: {e}"
                                )
                            _clog.log_collect_event(
                                "source_failed",
                                run_id=run_id,
                                category=cat.value,
                                source=name,
                                error=str(err)[:200],
                                duration_ms=int(sr.duration_ms or 0),
                            )
                        else:
                            cat_succeeded += 1
                            try:
                                _ckpt_repo.mark_done(
                                    run_id, cat.value, name, count
                                )
                            except Exception as e:
                                logger.warning(
                                    f"checkpoint mark_done failed: {e}"
                                )
                            _clog.log_collect_event(
                                "source_done",
                                run_id=run_id,
                                category=cat.value,
                                source=name,
                                items=count,
                                duration_ms=int(sr.duration_ms or 0),
                            )
                    sources_succeeded += cat_succeeded
                    sources_failed += cat_failed
                    _clog.log_collect_event(
                        "category_done",
                        run_id=run_id,
                        category=cat.value,
                        items=int(report.total),
                        duration_ms=cat_duration_ms,
                        sources_succeeded=cat_succeeded,
                        sources_failed=cat_failed,
                    )
                    # P0-1: 每 cat 完成立即推送 progress, 让前端轮询能
                    # 看到 sources_succeeded / items_ingested 增量
                    try:
                        _repo.update_progress(
                            run_id,
                            items_ingested=items_ingested,
                            sources_succeeded=sources_succeeded,
                        )
                    except Exception as e:
                        logger.warning(
                            f"update_progress (per-cat) failed: {e}"
                        )
                except Exception as e:
                    logger.warning(
                        f"checkpoint write failed for cat={cat.value}: {e}"
                    )
            except Exception as e:
                cat_duration_ms = int((_time.time() - cat_start) * 1000)
                logger.error(
                    f"_execute_catchup_run: cat={cat.value} crashed: {e}"
                )
                _clog.log_collect_event(
                    "category_failed",
                    run_id=run_id,
                    category=cat.value,
                    error=str(e)[:200],
                    duration_ms=cat_duration_ms,
                )

        # 6. 增量写 progress
        _repo.update_progress(
            run_id,
            items_ingested=items_ingested,
            sources_succeeded=sources_succeeded,
        )

        # 7. 触发 trend_rebuild (后台, 不阻塞)
        try:
            from backend.scheduler.jobs import trend_rebuild_job
            asyncio.create_task(trend_rebuild_job())
        except Exception as e:
            logger.warning(f"schedule trend_rebuild_job failed: {e}")

        # 8. v1.9: 跑 4 类数据完整性验证 (不阻塞终态)
        validation_errors = 0
        validation_warnings = 0
        try:
            vreport = validate_and_persist(run_id, since_iso, until_iso)
            validation_errors = sum(
                1 for i in vreport.issues if i.severity == "error"
            )
            validation_warnings = sum(
                1 for i in vreport.issues if i.severity == "warn"
            )
            logger.info(
                f"_execute_catchup_run: validation run_id={run_id} "
                f"total={len(vreport.issues)} errors={validation_errors} "
                f"warnings={validation_warnings}"
            )
        except Exception as e:
            logger.warning(f"validation crashed (ignored): {e}")

        # 9. 终态
        if sources_attempted > 0 and sources_succeeded == 0 and sources_skipped == 0:
            status = "failed"
            err = "all sources failed"
        elif sources_attempted > 0 and sources_succeeded < sources_attempted - sources_skipped:
            status = "partial"
            err = None
        else:
            status = "success"
            err = None
        _repo.finish(
            run_id,
            status=status,
            items_ingested=items_ingested,
            items_skipped=sources_skipped,
            sources_attempted=sources_attempted,
            sources_succeeded=sources_succeeded,
            error_msg=err,
        )
        # v1.9: collect_done 事件
        _clog.log_collect_event(
            "collect_done",
            run_id=run_id,
            mode=mode,
            status=status,
            items_ingested=items_ingested,
            sources_attempted=sources_attempted,
            sources_succeeded=sources_succeeded,
            sources_failed=sources_failed,
            sources_skipped=sources_skipped,
            validation_errors=validation_errors,
            validation_warnings=validation_warnings,
        )
        logger.info(
            f"_execute_catchup_run: run_id={run_id} finished status={status} "
            f"items_ingested={items_ingested} sources_succeeded={sources_succeeded} "
            f"sources_skipped={sources_skipped} val_errors={validation_errors}"
        )
    except Exception as e:
        logger.error(f"_execute_catchup_run: run_id={run_id} crashed: {e}")
        try:
            _repo.finish(
                run_id,
                status="failed",
                items_ingested=items_ingested,
                items_skipped=sources_skipped,
                sources_attempted=sources_attempted,
                sources_succeeded=sources_succeeded,
                error_msg=f"{type(e).__name__}: {str(e)[:200]}",
            )
        except Exception:
            pass
        # v1.9: 失败也写事件
        try:
            _clog.log_collect_event(
                "collect_done",
                run_id=run_id,
                mode=mode,
                status="failed",
                error=f"{type(e).__name__}: {str(e)[:200]}",
                items_ingested=items_ingested,
            )
        except Exception:
            pass
    finally:
        # 恢复原 sources + max_items
        if svc is not None:
            for cat, original in original_sources.items():
                if cat in svc.collectors:
                    svc.collectors[cat].sources = original
            for cat, orig_max in original_max_items.items():
                if cat in svc.collectors:
                    svc.collectors[cat].max_items = orig_max
        if mode == "manual":
            _current_manual_run = None


# ---------------------------------------------------------------------------
# Watchdog 防抖 helper
# ---------------------------------------------------------------------------
def should_enqueue_auto() -> bool:
    """watchdog 调用: 距上次 auto enqueue ≥ 5min 才允许再次触发.

    Returns True 如果可以触发, False 如果在防抖窗口内.
    """
    global _last_auto_enqueue_at
    if _last_auto_enqueue_at is None:
        return True
    return (datetime.now(timezone.utc) - _last_auto_enqueue_at).total_seconds() >= _AUTO_ENQUEUE_DEBOUNCE_S


def mark_auto_enqueued() -> None:
    """watchdog 调用: 标记本次 enqueue 时间"""
    global _last_auto_enqueue_at
    _last_auto_enqueue_at = datetime.now(timezone.utc)


__all__ = [
    "enqueue_catchup",
    "abort_current",
    "get_last_orphan_recovery_at",
    "set_last_orphan_recovery_at",
    "get_current_manual_run_id",
    "should_enqueue_auto",
    "mark_auto_enqueued",
]

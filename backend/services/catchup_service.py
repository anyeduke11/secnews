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

任务边界
--------
- B (Watchdog): 仅调用本模块的 ``enqueue_catchup`` 接口
- C (Service): 本文件实现主流程 ``run()`` + 选源 + 抓取 + 写库
- D (API): 通过 ``enqueue_catchup`` / ``abort_current`` 间接调用

Phase 8 初始版本 (B stub)
--------------------------
本版本是 B 任务的最小可用版本, 用于:
1. 让 watchdog 可触发追抓
2. 让 /api/catchup/* 接口可返回 202
3. C 任务会替换 ``_execute_catchup_run`` 的具体实现
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from backend.logging_config import logger as _root_logger
from backend.repository.catchup_repo import CatchupRepository, CatchupStatus

# Module-level state (Phase 8 watchdog 需要)
logger = _root_logger.bind(component="catchup_service")
_repo = CatchupRepository()

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
        f"max_per_source={max_per_source}"
    )

    # Fire-and-forget 后台执行
    asyncio.create_task(_execute_catchup_run(run.id, mode=mode))
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


async def _execute_catchup_run(run_id: int, *, mode: str) -> None:
    """C 任务: 实际追抓主流程.

    流程
    ----
    1. 读 run 配置 (categories / max_per_source)
    2. 选源: 跳过 ``source_stats.status='dead' AND last_checked_at < now-24h``
    3. 临时修改每个 collector.sources (过滤 dead) + max_items (cap)
    4. 复用 CollectionService.run_once() 跑并发抓取
    5. write progress (持续更新 ingested / succeeded)
    6. 触发 trend_rebuild_job (后台)
    7. finish: success (有 item) / partial (部分源失败) / failed (整轮炸)

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
    original_sources: dict = {}
    original_max_items: dict = {}
    target_cats: list = []
    svc = None

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
        _repo.update_progress(run_id, sources_attempted=sources_attempted)
        logger.info(
            f"_execute_catchup_run: run_id={run_id} mode={mode} "
            f"categories={[c.value for c in target_cats]} "
            f"sources={sources_attempted} (skipped {total_dead_skipped} dead) "
            f"max_per_source={run.max_per_source}"
        )

        # 4. 跑 (用 single-category run_one 路径)
        for cat in target_cats:
            if cat not in svc.collectors:
                continue
            try:
                report = await svc.run_one(cat)
                if report.results:
                    cat_result = report.results[0]
                    items_ingested += int(report.total)
                    if not cat_result.error:
                        sources_succeeded += len(svc.collectors[cat].sources)
            except Exception as e:
                logger.error(
                    f"_execute_catchup_run: cat={cat.value} crashed: {e}"
                )
        # 5. 增量写 progress
        _repo.update_progress(
            run_id,
            items_ingested=items_ingested,
            sources_succeeded=sources_succeeded,
        )

        # 6. 触发 trend_rebuild (后台, 不阻塞)
        try:
            from backend.scheduler.jobs import trend_rebuild_job
            asyncio.create_task(trend_rebuild_job())
        except Exception as e:
            logger.warning(f"schedule trend_rebuild_job failed: {e}")

        # 7. 终态
        if sources_attempted > 0 and sources_succeeded == 0:
            status = "failed"
            err = "all sources failed"
        elif sources_attempted > 0 and sources_succeeded < sources_attempted:
            status = "partial"
            err = None
        else:
            status = "success"
            err = None
        _repo.finish(
            run_id,
            status=status,
            items_ingested=items_ingested,
            items_skipped=0,
            sources_attempted=sources_attempted,
            sources_succeeded=sources_succeeded,
            error_msg=err,
        )
        logger.info(
            f"_execute_catchup_run: run_id={run_id} finished status={status} "
            f"items_ingested={items_ingested} sources_succeeded={sources_succeeded}"
        )
    except Exception as e:
        logger.error(f"_execute_catchup_run: run_id={run_id} crashed: {e}")
        try:
            _repo.finish(
                run_id,
                status="failed",
                items_ingested=items_ingested,
                items_skipped=0,
                sources_attempted=sources_attempted,
                sources_succeeded=sources_succeeded,
                error_msg=f"{type(e).__name__}: {str(e)[:200]}",
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

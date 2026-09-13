"""采集 run 支撑层 — 旁路写入 / 摘要富化 / 完成事件 / 单源单 collector 执行。

Batch 4 Task C 从 ``collection_service.py`` 物理搬出 (行为零变更, SQL 原样),
``collection_service.py`` 保留编排 facade。本模块职责:

- **旁路写入** — ``write_raw_items`` / ``write_crawler_runs`` /
  ``write_crawler_runs_for_source`` / ``write_collection_run`` /
  ``insert_running_row`` (collection_runs / crawler_runs / raw_items 表;
  R2 收缩批后写语句统一走 ``CollectionRepository``, 本模块只保留值
  计算 / 逐条异常隔离 / 日志)。
- **去重指纹** 见 ``collection_dedup`` (content_fingerprints)。
- **run 内步骤** — ``inject_custom_sources`` / ``enrich_and_recheck`` /
  ``rebuild_trend_and_log`` / ``invalidate_caches`` /
  ``schedule_url_content_check`` / ``publish_collect_done`` /
  ``evaluate_source_coverage_logged``。
- **单粒度执行** — ``run_one_collector_safe`` (单 collector 异常隔离) /
  ``run_single_source`` (单源采集), 由 facade 在锁内调用。
- 健康机: ``write_crawler_runs`` 内经 (name, category) 反查
  crawler_sources 后调 ``SourceHealthMachine.apply_run_result``
  (P1.2); ``backend/services/source_health_machine.py`` 本就是独立模块。

线程亲和约定: 同步 sqlite3 写函数必须在 ``asyncio.to_thread`` 工作线程内
调用 (get_connection 为 thread-local); async 函数内部保持原有的
to_thread 边界, 时序与搬出前完全一致。
"""
import asyncio
import hashlib
import time
from datetime import datetime, timezone
from typing import Any

from backend.cache import invalidate as cache_invalidate
from backend.domain.collection import CollectionReport, CollectionResult
from backend.domain.enums import Category, CollectorStatus
from backend.domain.models import HotspotItem
from backend.repository.collection_repo import CollectionRepository
from backend.repository.custom_source_repo import CustomSourceRepository
from backend.repository.db import get_connection
from backend.repository.hotspot_repo import HotspotRepository
from backend.services.collection_dedup import dedup_items, write_fingerprints

# P1: 保存后台 fire-and-forget task 引用 — 不保存引用时 asyncio.Task 可能被
# GC 回收中断 (RUF006)。done 时自动从集合移除。
_background_tasks: set = set()


def _spawn(task) -> None:
    """登记后台任务, 防止被 GC 提前回收。"""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# ---------------------------------------------------------------------------
# run 内步骤 (run_once / run_one 主流程调用)
# ---------------------------------------------------------------------------

def inject_custom_sources(collectors: dict, logger) -> None:
    """Phase 8 Addendum 8.4: 注入 custom_sources 到对应分类 collector。

    用户添加的源优先于兜底源（追加在最后），不覆盖原 sources。
    """
    try:
        custom_repo = CustomSourceRepository()
        for cat, c_list in collectors.items():
            extra = custom_repo.list_enabled_by_category(cat)
            if not extra:
                continue
            for c in c_list:
                existing_urls = {s.get("url") for s in c.sources}
                for s in extra:
                    if s["url"] not in existing_urls:
                        c.sources.append(s)
            logger.info(
                f"injected {len(extra)} custom sources for {cat.value}"
            )
    except Exception as e:
        # 表可能还未创建（首次启动 migration 没跑完）；不阻塞采集
        logger.warning(f"custom_source injection skipped: {e}")


async def enrich_and_recheck(items: list[HotspotItem], logger) -> list[HotspotItem]:
    """v1.9: 摘要富化 — 对含 HTML 元数据的 RSS 摘要，抓取实际文章内容。

    尽力而为，失败不阻塞主流程。P2-7: 富化后摘要复检 — 富化内容在质量
    门禁之后写入, 此前不过 ContentQualityGate (spam/乱码/长度)。不合格的
    富化摘要回退为空, 保留原标题/原摘要, 防止污染入库。
    P1.4 (v0.7.x): 单 item 异常隔离 — 单 item 异常仅丢该 item 的复检,
    不影响其余 item。
    """
    try:
        from backend.services.summary_enricher import batch_enrich
        items = await batch_enrich(items, max_concurrent=5)
        from backend.quality.content_quality_gate import check_summary_quality
        reverted = 0
        recheck_errors = 0
        for it in items:
            if not it.summary:
                continue
            try:
                flags = check_summary_quality(it.title or "", it.summary)
                if flags:
                    it.summary = None  # 富化摘要不合格 → 丢弃
                    reverted += 1
            except Exception as item_err:
                # 单 item 异常: 仅丢该 item 的复检, 保留原 summary
                # (避免污染其余 item), 但记录错误便于审计
                recheck_errors += 1
                logger.debug(
                    f"quality recheck failed for {getattr(it, 'id', '?')}: "
                    f"{type(item_err).__name__}: {str(item_err)[:80]}"
                )
        if reverted:
            logger.info(f"enriched summary reverted (low quality): {reverted}")
        if recheck_errors:
            logger.warning(
                f"enriched summary recheck had {recheck_errors} per-item errors"
            )
    except Exception as e:
        logger.warning(f"summary enrichment failed: {e}")
    return items


async def rebuild_trend_and_log(trend, logger) -> None:
    """重建 24h 趋势网格 (同步 sqlite3 操作, 放 thread pool)。"""
    try:
        trend_count = await asyncio.to_thread(trend.rebuild, 24)
        logger.info(f"trend rebuilt: {trend_count} points")
    except Exception as e:
        logger.error(f"trend rebuild failed: {e}")


def invalidate_caches(logger) -> None:
    """Phase 4: 采集完成后失效 hotspots/trends 缓存。"""
    try:
        cache_invalidate("hotspots:*")
        cache_invalidate("trends:*")
    except Exception as e:
        logger.warning(f"cache invalidation failed: {e}")


def schedule_url_content_check(logger) -> None:
    """Phase 3.5: 异步触发 URL 内容验证（不阻塞 return）。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            from backend.quality.jobs import run_url_content_check
            _spawn(loop.create_task(run_url_content_check()))
    except Exception as e:
        logger.warning(f"schedule url_content_check failed: {e}")


def publish_collect_done(
    results: list[CollectionResult], total: int, duration_ms: int, logger
) -> None:
    """Phase 6: SSE 推送采集完成事件 (collect_done)。"""
    try:
        from backend.core.events import publish_event
        categories_done = [r.category.value for r in results]
        _spawn(asyncio.ensure_future(
            publish_event("collect_done", {
                "categories": categories_done,
                "total": total,
                "duration_ms": duration_ms,
                "failures": [r.category.value for r in results if r.error],
            })
        ))
    except Exception as e:
        logger.warning(f"sse publish failed: {e}")


async def evaluate_source_coverage_logged(
    report, logger, label: str = ""
) -> None:
    """Phase 9 招标源质量门禁：评估每源产出 + 覆盖度，写 source_stats +
    coverage_runs + 告警日志。同步 DB 操作放 thread pool。

    ``label``: 日志前缀差异化 (run_once 传 "", run_one 传分类标签)。
    """
    try:
        from backend.quality.source_coverage import evaluate_source_coverage
        cov = await asyncio.to_thread(evaluate_source_coverage, report)
        logger.info(
            f"source coverage{label}: "
            f"alerts={len(cov.alerts)} "
            f"dead={len(cov.dead_sources)} stale={len(cov.stale_sources)}"
        )
    except Exception as e:
        logger.warning(f"source coverage evaluation failed: {e}")


# ---------------------------------------------------------------------------
# 单粒度执行 (facade 在锁内调用)
# ---------------------------------------------------------------------------

async def run_one_collector_safe(
    category: Category, collector, since: str | None = None, *, logger
) -> CollectionResult:
    """跑单 collector，异常隔离

    Phase 9 招标源质量门禁：从 ``collector.last_source_results``
    读每源产出，填到 ``CollectionResult.source_results``。

    Phase 8: 起始时 INSERT 一行 collection_runs status='running',
    供 catchup_watchdog 检测孤儿. 结束时由 write_collection_run
    UPDATE 同一行. INSERT 失败 → run_id=None (走老路径).

    P2-3: ``since`` 透传给 collector.collect 做时间窗口过滤。
    """
    start_ms = time.time()
    started_at = datetime.now(timezone.utc)
    # Phase 8: 起始插 'running' 行
    run_id = insert_running_row(category, started_at, logger)
    try:
        items: list[HotspotItem] = await collector.collect(since=since)
        # Phase 8: dedup using simhash fingerprints
        items = await asyncio.to_thread(dedup_items, items, logger)
        duration_ms = int((time.time() - start_ms) * 1000)
        fallback_count = sum(1 for it in items if it.is_fallback)
        # Phase 9 招标源质量门禁：取 collector 的 per-source 结果
        source_results = list(
            getattr(collector, "last_source_results", []) or []
        )
        return CollectionResult(
            category=category,
            items=items,
            item_count=len(items),
            fallback_count=fallback_count,
            source_results=source_results,
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            run_id=run_id,
        )
    except Exception as e:
        import traceback
        logger.error(f"{category.value} collector crashed: {e}\n{traceback.format_exc()}")
        return CollectionResult(
            category=category,
            items=[],
            item_count=0,
            fallback_count=0,
            duration_ms=int((time.time() - start_ms) * 1000),
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            run_id=run_id,
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )


async def run_single_source(
    source_id: str, collectors: dict, logger
) -> dict:
    """单源采集 (原 CollectionService._run_one_source_locked 持锁路径)。

    Returns a dict with: source_id, fetched_count, accepted_count,
    duration_ms, status ('success'|'failed'), error_msg
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM crawler_sources WHERE id = ?", (source_id,)
    ).fetchone()
    if row is None:
        return {
            "source_id": source_id,
            "fetched_count": 0,
            "accepted_count": 0,
            "duration_ms": 0,
            "status": "failed",
            "error_msg": f"source {source_id} not found in crawler_sources",
        }

    source = dict(row)
    category_str = source.get("category", "")
    try:
        category = Category(category_str)
    except (ValueError, KeyError):
        return {
            "source_id": source_id,
            "fetched_count": 0,
            "accepted_count": 0,
            "duration_ms": 0,
            "status": "failed",
            "error_msg": f"unknown category: {category_str}",
        }

    if category not in collectors:
        return {
            "source_id": source_id,
            "fetched_count": 0,
            "accepted_count": 0,
            "duration_ms": 0,
            "status": "failed",
            "error_msg": f"no collector for category: {category_str}",
        }

    start_ms = time.time()
    # P2-6: 在多 collector 中找到目标源所属的 collector (按源名匹配)
    source_name = source.get("name") or source_id
    collector = None
    for c in collectors[category]:
        c_names = {s.get("name") for s in (c.sources or [])}
        if source_name in c_names:
            collector = c
            break
    if collector is None:
        collector = collectors[category][0]
    # started_at 未入返回值 — 仅作时间锚点供未来 per-source 耗时统计
    _started_at = datetime.now(timezone.utc)
    del _started_at

    try:
        # P2-0: 传目标源名 — 只抓该源, 不再整分类采集
        items = await collector.collect(only_source=source_name)
        duration_ms = int((time.time() - start_ms) * 1000)
        accepted_count = len(items) if items else 0
        # cadence 修正批 (存活/有用分离): collect() 把每源 SourceResult 暴露在
        # last_source_results, 取过滤前候选数作存活口径 (未接线路径回落 accepted)
        raw_count = max(
            (
                sr.fetched_count
                for sr in getattr(collector, "last_source_results", []) or []
                if sr.source_name == source_name
            ),
            default=0,
        )
        fetched_count = max(raw_count, accepted_count)

        # Write raw_items directly
        if items:
            try:
                repo = HotspotRepository()
                await asyncio.to_thread(repo.upsert_many, items)
                # P0-5: 入库成功后补写去重指纹
                await asyncio.to_thread(write_fingerprints, items, logger)
            except Exception as e:
                logger.warning(f"run_one_source upsert failed: {e}")

        # Write crawler_runs
        try:
            await asyncio.to_thread(
                write_crawler_runs_for_source,
                source_id, source.get("category", ""),
                fetched_count, duration_ms, None, accepted_count,
            )
        except Exception as e:
            logger.warning(f"run_one_source crawler_runs write failed: {e}")

        return {
            "source_id": source_id,
            "fetched_count": fetched_count,
            "accepted_count": accepted_count,
            "duration_ms": duration_ms,
            "status": "success" if accepted_count > 0 else "partial",
            "error_msg": None,
        }
    except Exception as e:
        duration_ms = int((time.time() - start_ms) * 1000)
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        logger.error(f"run_one_source {source_id} failed: {error_msg}")

        # Write crawler_runs with failure
        try:
            await asyncio.to_thread(
                write_crawler_runs_for_source,
                source_id, source.get("category", ""),
                0, duration_ms, error_msg,
            )
        except Exception as e2:
            logger.warning(f"run_one_source crawler_runs write failed: {e2}")

        return {
            "source_id": source_id,
            "fetched_count": 0,
            "accepted_count": 0,
            "duration_ms": duration_ms,
            "status": "failed",
            "error_msg": error_msg,
        }


async def run_category_locked(
    category: Category,
    since: str | None,
    collectors: dict,
    repo,
    trend,
    logger,
) -> CollectionReport:
    """单分类执行 (原 CollectionService._run_one_locked 持锁路径)。

    P2-6: 该分类下全部 collectors 依次执行并合并结果。
    """
    started_at = datetime.now(timezone.utc)
    start_ms = time.time()

    if category not in collectors:
        raise ValueError(f"unknown category: {category}")

    c_list = collectors[category]
    results: list[CollectionResult] = []
    for c in c_list:
        r = await run_one_collector_safe(category, c, since=since, logger=logger)
        results.append(r)

    # 合并所有 collector 的 items
    merged_items: list[HotspotItem] = []
    for r in results:
        merged_items.extend(r.items)
    merged_error = next((r.error for r in results if r.error), None)
    # merged_source_results 聚合各 collector 的 source_results — 现未消费,
    # 保留供 Phase 后续按 source 维度统计成功率
    _merged_source_results = [
        sr for r in results for sr in (r.source_results or [])
    ]
    del _merged_source_results
    merged_fallback = sum(r.fallback_count for r in results)
    # 用第一个 result 承载合并 (run_id 以它为准, collection_runs 逐条写)
    # result 实际未被消费 — upsert_many 已用 merged_items
    _result = results[0] if results else None
    del _result

    if merged_items:
        try:
            await asyncio.to_thread(repo.upsert_many, merged_items)
        except Exception as e:
            logger.error(f"upsert failed: {e}")
            merged_error = merged_error or f"upsert failed: {e}"

        # P0-5: 入库成功后补写去重指纹
        try:
            await asyncio.to_thread(write_fingerprints, merged_items, logger)
        except Exception as e:
            logger.warning(f"fingerprint write skipped: {e}")

    await rebuild_trend_and_log(trend, logger)

    # 逐 collector 写 collection_runs 审计行
    for r in results:
        try:
            await asyncio.to_thread(write_collection_run, r, logger)
        except Exception as e:
            logger.warning(f"collection_runs write failed: {e}")

    # Phase 0 (Crawler v2): 旁路写入 crawler_runs (逐 collector)
    for r in results:
        try:
            await asyncio.to_thread(write_crawler_runs, r, logger)
        except Exception as e:
            logger.warning(f"crawler_runs write skipped: {e}")

    # Phase 4: 单分类采集后也失效缓存
    invalidate_caches(logger)

    finished_at = datetime.now(timezone.utc)
    duration_ms = int((time.time() - start_ms) * 1000)
    # 合并报告: 用合并后的 items/source_results/error (P2-6 多 collector)
    merged_report_item_count = sum(r.item_count for r in results)
    report = CollectionReport(
        total=merged_report_item_count,
        success_count=0 if merged_error else 1,
        failed_count=1 if merged_error else 0,
        fallback_count=merged_fallback,
        duration_ms=duration_ms,
        started_at=started_at,
        finished_at=finished_at,
        failures=[{"category": category.value, "error": merged_error}] if merged_error else [],
        results=results,
    )

    # Phase 9 招标源质量门禁：单分类 collect 也走 source coverage 评估
    await evaluate_source_coverage_logged(
        report, logger, label=f" ({category.value})"
    )

    return report


# ---------------------------------------------------------------------------
# 旁路写入 (collection_runs / crawler_runs / raw_items)
# ---------------------------------------------------------------------------

def insert_running_row(category: Category, started_at, logger) -> int | None:
    """Phase 8: 在 collection_runs 插一行 status='running', 供 watchdog 检测孤儿.

    Returns: 新行 id, 或 None (INSERT 失败时).
    """
    try:
        return CollectionRepository().insert_running_run(
            category.value, started_at.isoformat()
        )
    except Exception as e:
        # 迁移未跑 / DB lock / 其它错误 — 不阻塞采集
        logger.warning(
            f"insert running row for {category.value} failed: {e}"
        )
        return None


def write_raw_items(
    items: list[Any], results: list[CollectionResult], logger
) -> None:
    """Phase 0 (Crawler v2): 旁路写入 raw_items 表。

    从 items 和 results 中提取源信息，写入 raw_items 表。
    不阻塞主流程，失败只打 warning。
    """
    if not items:
        return

    # 构建 item_id -> source_id 映射
    item_source_map: dict[str, str] = {}
    for r in results:
        if r.error:
            continue
        for it in r.items:
            item_source_map[str(it.id)] = str(getattr(it, "source", ""))

    repo = CollectionRepository()
    written = 0
    for item in items:
        try:
            item_id = str(item.id) if hasattr(item, "id") else ""
            if not item_id:
                continue
            source_id = item_source_map.get(item_id, "")
            title = str(item.title) if hasattr(item, "title") else ""
            url = str(item.url) if hasattr(item, "url") else ""
            summary = str(item.summary or "") if hasattr(item, "summary") else ""
            published_at = (
                str(item.published_at) if hasattr(item, "published_at")
                and item.published_at else ""
            )
            # content_hash 用于去重
            content_hash = hashlib.sha256(
                (title + url + summary).encode("utf-8")
            ).hexdigest()[:16]

            repo.insert_raw_item(
                item_id, source_id, title, url, summary,
                content_hash, published_at,
            )
            written += 1
        except Exception:
            # 单条失败不阻塞整体
            continue

    logger.debug(f"raw_items written: {written}")


def write_crawler_runs(result: CollectionResult, logger) -> None:
    """Phase 0 (Crawler v2): 旁路写入 crawler_runs 表。

    与 write_collection_run 并行运行，记录每源每轮抓取统计。

    P1.2 (v0.7.x): 写 crawler_runs 后, 通过 (name, category) 反查
    ``crawler_sources.id`` 并触发 ``SourceHealthMachine.apply_run_result``
    — 此前 ``run_once`` 路径不调健康机 (只有 scheduler per-source tick
    会调), 导致 RSS 空 / 抓取失败的源连续多轮不更新 consecutive_failures,
    健康口径失真。此处补齐后, 失败源会自动从 active → stale → dead。
    """
    try:
        source_results = result.source_results or []
        if not source_results:
            return

        # conn 注入 repo: crawler_runs 写入与健康机反查 SELECT 落在同一连接。
        conn = get_connection()
        repo = CollectionRepository(conn)
        written = 0
        health_results: list[dict] = []
        for sr in source_results:
            source_name = sr.source_name
            status = "failed" if sr.error_msg else (
                "partial" if sr.item_count == 0 else "success"
            )
            # cadence 修正批 (存活/有用分离): fetched = 过滤前候选数 (存活口径),
            # accepted = 最终条目数 (有用口径)。此前两列同写 item_count, 招标源
            # "40 条锚点 / 0 条安全相关" 被健康机当成 0 抓取 → dead。
            fetched_count = sr.fetched_count
            accepted_count = sr.item_count
            duration_ms = sr.duration_ms
            started_at = result.started_at.isoformat()
            finished_at = (
                result.finished_at.isoformat()
                if result.finished_at else ""
            )

            repo.insert_crawler_run(
                source_name, result.category.value,
                started_at, finished_at, status,
                fetched_count, accepted_count,
                sr.error_msg or "", duration_ms,
            )
            written += 1

            # P1.2: 反查 crawler_sources.id 触发健康机。
            # 用 name + category 匹配 (id 是 slug, name 在 source dict 是原名)。
            # 找不到 → skip (源未 seed 进 crawler_sources, 不影响主流程)。
            src_row = conn.execute(
                "SELECT id FROM crawler_sources "
                "WHERE name = ? AND category = ? LIMIT 1",
                (source_name, result.category.value),
            ).fetchone()
            if src_row is None:
                continue
            source_id = str(src_row["id"])
            try:
                from backend.services.source_health_machine import (
                    SourceHealthMachine,
                )
                hm = SourceHealthMachine()
                health = hm.apply_run_result(
                    source_id,
                    {
                        "fetched_count": fetched_count,
                        "accepted_count": accepted_count,
                        "status": status,
                        "duration_ms": duration_ms,
                        "error_msg": sr.error_msg or "",
                    },
                )
                health_results.append(health)
            except Exception as e:
                logger.debug(
                    f"apply_run_result skipped for {source_id}: {e}"
                )

        if health_results:
            transitioned = [
                h for h in health_results
                if (h.get("transition") not in ("none", "success_reset")
                and "incremented" in h.get("transition", ""))
                or "to_" in h.get("transition", "")
            ]
            if transitioned:
                logger.info(
                    f"crawler_runs: {len(transitioned)} source health transitions: "
                    + ", ".join(
                        f"{h['source_id']}→{h['new_status']}(f={h['consecutive_failures']})"
                        for h in transitioned[:5]
                    )
                )
        logger.debug(f"crawler_runs written: {written}")
    except Exception as e:
        logger.warning(f"crawler_runs write skipped: {e}")


def write_crawler_runs_for_source(
    source_id: str,
    category: str,
    fetched_count: int,
    duration_ms: int,
    error_msg: str | None,
    accepted_count: int | None = None,
) -> None:
    """Write a single crawler_runs row for a source run.

    cadence 修正批: ``accepted_count`` 可与 ``fetched_count`` 分离 (存活/有用);
    不传时沿用旧语义 (两列同值)。status 按 accepted 判 success/partial。
    """
    now = datetime.now(timezone.utc).isoformat()
    if accepted_count is None:
        accepted_count = fetched_count
    status = "failed" if error_msg else (
        "partial" if accepted_count == 0 else "success"
    )
    CollectionRepository().insert_crawler_run(
        source_id, category, now, now, status,
        fetched_count, accepted_count, error_msg or "", duration_ms,
    )


def write_collection_run(result: CollectionResult, logger) -> None:
    """写入 collection_runs 表 (Phase 8: UPDATE 起始行, 老路径 fallback INSERT)"""
    try:
        repo = CollectionRepository()
        status = CollectorStatus.FAILED if result.error else (
            CollectorStatus.PARTIAL if result.fallback_count > 0 else CollectorStatus.SUCCESS
        )
        finished_at_iso = (
            result.finished_at.isoformat() if result.finished_at else None
        )
        if result.run_id is not None:
            # Phase 8: UPDATE 起始 'running' 行
            repo.update_run_finished(
                int(result.run_id),
                finished_at_iso,
                status.value,
                result.item_count,
                result.fallback_count,
                result.error,
            )
        else:
            # 老路径: 直接 INSERT (起始行 INSERT 失败时)
            repo.insert_run(
                result.category.value,
                result.started_at.isoformat(),
                finished_at_iso,
                status.value,
                result.item_count,
                result.fallback_count,
                result.error,
            )
    except Exception as e:
        logger.error(f"write collection_run failed: {e}")

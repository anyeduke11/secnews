"""统一编排 5 个 collector → 写 DB → 写 collection_runs → rebuild trend

Phase 3 Task 4 introduces ``CollectionService`` — the single entry
point for running a full collection cycle. The service:

1. **Concurrent execution** — every configured collector is launched as
   an independent ``asyncio`` task via ``asyncio.gather``. A single
   collector crash never aborts the whole run.
2. **Repository writes** — successful collector outputs are flattened
   and passed to :meth:`HotspotRepository.upsert_many` in one batch.
3. **Trend rebuild** — after a successful upsert, the 24h trend grid
   is recomputed from the freshly-written hotspots.
4. **Audit log** — each per-category outcome is written to
   ``collection_runs`` with a derived status (``SUCCESS`` /
   ``PARTIAL`` / ``FAILED``).

The service is intentionally a thin orchestration layer. It depends on
the canonical repository / domain types so all writes go through the
same validation / error-handling path as the rest of the backend.
"""
import asyncio
import hashlib
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, ClassVar

from backend.cache import invalidate as cache_invalidate
from backend.collectors.ai_collector import AICollector
from backend.collectors.ai_security_collector import AISecurityCollector
from backend.collectors.base import BaseCollector
from backend.collectors.bid_collector import BidCollector
from backend.collectors.finance_collector import FinanceCollector
from backend.collectors.gdelt_collector import GDELTCollector  # P2-6
from backend.collectors.github_collector import GitHubCollector
from backend.collectors.hn_collector import HNCollector  # P2-6
from backend.collectors.openbb_collector import OpenBBCollector  # P2-6
from backend.collectors.ossinsight_collector import OSSInsightCollector  # P2-6
from backend.collectors.reddit_collector import RedditCollector  # P2-6
from backend.collectors.security_collector import SecurityCollector
from backend.collectors.startup_collector import StartupCollector
from backend.collectors.tech_collector import TechCollector  # Phase 25 P1
from backend.collectors.telegram_collector import TelegramCollector  # P2-6
from backend.domain.collection import CollectionReport, CollectionResult
from backend.services.simhash import (
    canonicalize_url,
    hamming_distance,
    normalize_title,
    simhash,
)

# SQLite BIGINT is signed 64-bit; simhash returns unsigned 64-bit.
_SIGNED_64_MASK = 0xFFFFFFFFFFFFFFFF
_SIGNED_64_OFFSET = 1 << 64


def _to_signed_64(val: int) -> int:
    """Convert unsigned 64-bit integer to signed 64-bit for SQLite storage."""
    return val - _SIGNED_64_OFFSET if val >= (1 << 63) else val


def _from_signed_64(val: int) -> int:
    """Convert signed 64-bit integer back to unsigned 64-bit."""
    return val + _SIGNED_64_OFFSET if val < 0 else val

from backend.domain.enums import Category, CollectorStatus
from backend.domain.models import HotspotItem
from backend.logging_config import logger
from backend.parsers.bid_extractor import extract_all as extract_bid_fields
from backend.repository.bid_detail_repo import BidDetailRepo
from backend.repository.custom_source_repo import CustomSourceRepository
from backend.repository.db import get_connection
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.trend_repo import TrendRepository

# P1: 保存后台 fire-and-forget task 引用 — 不保存引用时 asyncio.Task 可能被
# GC 回收中断 (RUF006)。done 时自动从集合移除。
_background_tasks: set = set()


def _spawn(task) -> None:
    """登记后台任务, 防止被 GC 提前回收。"""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)



class CollectionService:
    """统一编排所有 collector"""

    # Phase 39: 模块级变量, 跟踪最近一次 run_once 的产出
    # (key reasons: 1) 避免每次新 CollectionService 实例的 state 丢失;
    #                2) 跨请求可读, 不需要注入到 HotspotService)
    # 用 dict 包装避免 global 关键字
    _latest_run: ClassVar[dict[str, Any]] = {"count": 0, "at": None}  # 类级共享运行状态

    def __init__(self):
        # P2-6: collectors 改为 dict[Category, list[BaseCollector]] — 支持
        # 每分类多个 collector (此前 1:1, 6 个已实现 collector 无法接线)。
        # 新接入: HN/Reddit/Telegram/OSSInsight → TECH, GDELT → SECURITY,
        # OpenBB → FINANCE (异常隔离在 _run_one_safe, 单源失败不阻塞)。
        self.collectors: dict[Category, list[BaseCollector]] = {
            Category.AI: [AICollector()],
            Category.AI_SECURITY: [AISecurityCollector()],
            Category.SECURITY: [SecurityCollector(), GDELTCollector()],
            Category.FINANCE: [FinanceCollector(), OpenBBCollector()],
            Category.STARTUP: [StartupCollector()],
            Category.BID: [BidCollector()],
            Category.GITHUB: [GitHubCollector()],
            Category.TECH: [
                TechCollector(),  # Phase 25 P1
                HNCollector(),
                RedditCollector(),
                TelegramCollector(),
                OSSInsightCollector(),
            ],
        }
        self.repo = HotspotRepository()
        self.trend = TrendRepository()
        self.logger = logger.bind(component="collection_service")
        # Phase 32: asyncio.Lock 防 run_once 重叠 — scheduler 周期跑和 POST
        # /api/refresh 手动触发共用同一把锁, 同一时刻只允许一个采集在跑.
        self._lock = asyncio.Lock()

    async def run_once(self) -> CollectionReport:
        """并发跑所有 collector → upsert DB → rebuild trend → 写 collection_runs

        Phase 32: 整体包在 self._lock 里, 防 scheduler 周期任务和手动刷新同时跑.
        排队策略: 后到的 caller 等锁释放, 然后正常跑一次 (不感知"刚跑过").
        """
        async with self._lock:
            return await self._run_once_locked()

    async def _run_once_locked(self) -> CollectionReport:
        started_at = datetime.now(timezone.utc)
        start_ms = time.time()
        self.logger.info("collection started")

        # Phase 8 Addendum 8.4: 注入 custom_sources 到对应分类 collector
        # 用户添加的源优先于兜底源（追加在最后），不覆盖原 sources。
        try:
            custom_repo = CustomSourceRepository()
            for cat, c_list in self.collectors.items():
                extra = custom_repo.list_enabled_by_category(cat)
                if not extra:
                    continue
                for c in c_list:
                    existing_urls = {s.get("url") for s in c.sources}
                    for s in extra:
                        if s["url"] not in existing_urls:
                            c.sources.append(s)
                self.logger.info(
                    f"injected {len(extra)} custom sources for {cat.value}"
                )
        except Exception as e:
            # 表可能还未创建（首次启动 migration 没跑完）；不阻塞采集
            self.logger.warning(f"custom_source injection skipped: {e}")

        # P2-6: 每分类跑其全部 collectors (gather 每分类下的所有 collector 任务)
        all_tasks = []
        for cat, c_list in self.collectors.items():
            for c in c_list:
                all_tasks.append(asyncio.create_task(self._run_one_safe(cat, c)))
        results = await asyncio.gather(*all_tasks, return_exceptions=False)

        # 合并所有 items
        all_items: list[HotspotItem] = []
        for r in results:
            all_items.extend(r.items)

        # v1.9: 摘要富化 — 对含 HTML 元数据的 RSS 摘要，抓取实际文章内容
        # 尽力而为，失败不阻塞主流程
        if all_items:
            try:
                from backend.services.summary_enricher import batch_enrich
                all_items = await batch_enrich(all_items, max_concurrent=5)
                # P2-7: 富化后摘要复检 — 富化内容在质量门禁之后写入, 此前
                # 不过 ContentQualityGate (spam/乱码/长度)。不合格的富化
                # 摘要回退为空, 保留原标题/原摘要, 防止污染入库。
                # P1.4 (v0.7.x): 单 item 异常隔离 — 此前 try/except 包整个
                # for 循环, 单个 item 触发 check 异常 → 整个 batch 的复检
                # 跳过, 全部以原 summary 入库 (可能含垃圾内容)。
                # 改为 per-item try/except, 单 item 异常仅丢该 item 的复检,
                # 不影响其余 item。
                from backend.quality.content_quality_gate import check_summary_quality
                reverted = 0
                recheck_errors = 0
                for it in all_items:
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
                        self.logger.debug(
                            f"quality recheck failed for {getattr(it, 'id', '?')}: "
                            f"{type(item_err).__name__}: {str(item_err)[:80]}"
                        )
                if reverted:
                    self.logger.info(f"enriched summary reverted (low quality): {reverted}")
                if recheck_errors:
                    self.logger.warning(
                        f"enriched summary recheck had {recheck_errors} per-item errors"
                    )
            except Exception as e:
                self.logger.warning(f"summary enrichment failed: {e}")

        # 写 DB — Phase 9 修复：放到 thread pool 避免阻塞 event loop
        # P2-8: upsert 失败必须反映到报告 (此前仅 logger.error, result.error
        # 仍为 None → collection_runs 记 SUCCESS + SSE 推"成功", 用户被误导)
        upsert_error: str | None = None
        if all_items:
            try:
                upserted = await asyncio.to_thread(self.repo.upsert_many, all_items)
                self.logger.info(f"upserted {upserted} items")
            except Exception as e:
                upsert_error = f"upsert failed: {type(e).__name__}: {str(e)[:200]}"
                self.logger.error(upsert_error)
                # 不中断其余旁路写入, 但报告记为失败

            # P0-5: 入库成功后补写去重指纹 (FK 依赖 hotspot 行已存在)
            try:
                await asyncio.to_thread(self._write_fingerprints, all_items)
            except Exception as e:
                self.logger.warning(f"fingerprint write skipped: {e}")

            # Phase 0 (Crawler v2): 旁路写入 raw_items（不阻塞主流程）
            try:
                await asyncio.to_thread(self._write_raw_items, all_items, results)
            except Exception as e:
                self.logger.warning(f"raw_items write skipped: {e}")

            # Phase 1.3: 标讯结构化字段写入 bid_details（不阻塞主流程）
            try:
                await asyncio.to_thread(self._write_bid_details, all_items)
            except Exception as e:
                self.logger.warning(f"bid_details write skipped: {e}")

        # 重建趋势 — Phase 9 修复：trend.rebuild 是同步 sqlite3 操作，放 thread pool
        try:
            trend_count = await asyncio.to_thread(self.trend.rebuild, 24)
            self.logger.info(f"trend rebuilt: {trend_count} points")
        except Exception as e:
            self.logger.error(f"trend rebuild failed: {e}")

        # 写 collection_runs — Phase 9 修复：同步 DB 写，放 thread pool
        for r in results:
            await asyncio.to_thread(self._write_collection_run, r)

        # Phase 0 (Crawler v2): 旁路写入 crawler_runs（不阻塞主流程）
        for r in results:
            try:
                await asyncio.to_thread(self._write_crawler_runs, r)
            except Exception as e:
                self.logger.warning(f"crawler_runs write skipped: {e}")

        # 统计 (须在 SSE 推送之前算好 total/duration_ms, 否则引用未赋值局部变量)
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((time.time() - start_ms) * 1000)
        total = sum(r.item_count for r in results)
        fallback = sum(r.fallback_count for r in results)
        failures = [
            {"category": r.category.value, "error": r.error}
            for r in results if r.error
        ]
        # P2-8: upsert 失败合并进 failures (全分类级)
        if upsert_error:
            failures.append({"category": "*", "error": upsert_error})

        # Phase 4: 采集完成后失效 hotspots/trends 缓存
        try:
            cache_invalidate("hotspots:*")
            cache_invalidate("trends:*")
        except Exception as e:
            self.logger.warning(f"cache invalidation failed: {e}")

        # Phase 3.5: 异步触发 URL 内容验证（不阻塞 return）
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                from backend.quality.jobs import run_url_content_check
                _spawn(loop.create_task(run_url_content_check()))
        except Exception as e:
            self.logger.warning(f"schedule url_content_check failed: {e}")

        # Phase 6: SSE 推送采集完成事件
        try:
            from backend.api.events import publish_event
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
            self.logger.warning(f"sse publish failed: {e}")

        report = CollectionReport(
            total=total,
            success_count=sum(1 for r in results if not r.error),
            failed_count=sum(1 for r in results if r.error) + (1 if upsert_error else 0),
            fallback_count=fallback,
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=finished_at,
            failures=failures,
            results=list(results),
        )

        # Phase 9 招标源质量门禁：评估每源产出 + 覆盖度，写 source_stats +
        # coverage_runs + 告警日志。同步 DB 操作放 thread pool。
        try:
            from backend.quality.source_coverage import evaluate_source_coverage
            cov = await asyncio.to_thread(evaluate_source_coverage, report)
            self.logger.info(
                f"source coverage: alerts={len(cov.alerts)} "
                f"dead={len(cov.dead_sources)} stale={len(cov.stale_sources)}"
            )
        except Exception as e:
            self.logger.warning(f"source coverage evaluation failed: {e}")

        self.logger.info(
            f"collection finished: total={total}, success={report.success_count}, "
            f"failed={report.failed_count}, duration={duration_ms}ms"
        )

        # Phase 39: 记录最新一次 run_once 的产出 (供 Header "新增 X 条" 显示)
        # 注意: 即使本次 run_once 全失败 (total=0), 也更新 at, 让前端能感知到
        # 后端"刚跑过"
        CollectionService._latest_run["count"] = total
        CollectionService._latest_run["at"] = finished_at

        return report

    async def run_one(self, category: Category, since: str | None = None) -> CollectionReport:
        """单分类执行（手动触发 / 重试）。

        P2-1: 与 run_once 共用 self._lock — 此前仅 run_once 持锁,
        run_one / run_one_source / catchup 并发写 + 共享 collector 可变
        状态 (self.sources) 互相覆盖, SQLite 靠 busy_timeout 硬扛。

        P2-3: ``since`` — catchup 追抓窗口, 透传给 collector 做时间过滤。
        """
        async with self._lock:
            return await self._run_one_locked(category, since=since)

    async def _run_one_locked(self, category: Category, since: str | None = None) -> CollectionReport:
        """单分类执行 (持锁路径)。

        P2-6: 该分类下全部 collectors 依次执行并合并结果。
        """
        started_at = datetime.now(timezone.utc)
        start_ms = time.time()

        if category not in self.collectors:
            raise ValueError(f"unknown category: {category}")

        c_list = self.collectors[category]
        results: list[CollectionResult] = []
        for c in c_list:
            r = await self._run_one_safe(category, c, since=since)
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
                await asyncio.to_thread(self.repo.upsert_many, merged_items)
            except Exception as e:
                self.logger.error(f"upsert failed: {e}")
                merged_error = merged_error or f"upsert failed: {e}"

            # P0-5: 入库成功后补写去重指纹
            try:
                await asyncio.to_thread(self._write_fingerprints, merged_items)
            except Exception as e:
                self.logger.warning(f"fingerprint write skipped: {e}")

        try:
            await asyncio.to_thread(self.trend.rebuild, 24)
        except Exception as e:
            self.logger.error(f"trend rebuild failed: {e}")

        # 逐 collector 写 collection_runs 审计行
        for r in results:
            try:
                await asyncio.to_thread(self._write_collection_run, r)
            except Exception as e:
                self.logger.warning(f"collection_runs write failed: {e}")

        # Phase 0 (Crawler v2): 旁路写入 crawler_runs (逐 collector)
        for r in results:
            try:
                await asyncio.to_thread(self._write_crawler_runs, r)
            except Exception as e:
                self.logger.warning(f"crawler_runs write skipped: {e}")

        # Phase 4: 单分类采集后也失效缓存
        try:
            cache_invalidate("hotspots:*")
            cache_invalidate("trends:*")
        except Exception as e:
            self.logger.warning(f"cache invalidation failed: {e}")

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
        try:
            from backend.quality.source_coverage import evaluate_source_coverage
            cov = await asyncio.to_thread(evaluate_source_coverage, report)
            self.logger.info(
                f"source coverage ({category.value}): "
                f"alerts={len(cov.alerts)} dead={len(cov.dead_sources)} "
                f"stale={len(cov.stale_sources)}"
            )
        except Exception as e:
            self.logger.warning(f"source coverage evaluation failed: {e}")

        return report

    async def run_one_source(self, source_id: str) -> dict:
        """Run collection for a single source by its crawler_sources ID.

        P2-1: 与 run_once 共用 self._lock (防并发写与共享状态覆盖)。

        Returns a dict with: source_id, fetched_count, accepted_count,
        duration_ms, status ('success'|'failed'), error_msg
        """
        async with self._lock:
            return await self._run_one_source_locked(source_id)

    async def _run_one_source_locked(self, source_id: str) -> dict:
        """单源采集 (持锁路径)。"""
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

        if category not in self.collectors:
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
        for c in self.collectors[category]:
            c_names = {s.get("name") for s in (c.sources or [])}
            if source_name in c_names:
                collector = c
                break
        if collector is None:
            collector = self.collectors[category][0]
        # started_at 未入返回值 — 仅作时间锚点供未来 per-source 耗时统计
        _started_at = datetime.now(timezone.utc)
        del _started_at

        try:
            # P2-0: 传目标源名 — 只抓该源, 不再整分类采集
            items = await collector.collect(only_source=source_name)
            duration_ms = int((time.time() - start_ms) * 1000)
            fetched_count = len(items) if items else 0
            accepted_count = fetched_count

            # Write raw_items directly
            if items:
                try:
                    repo = HotspotRepository()
                    await asyncio.to_thread(repo.upsert_many, items)
                    # P0-5: 入库成功后补写去重指纹
                    await asyncio.to_thread(self._write_fingerprints, items)
                except Exception as e:
                    self.logger.warning(f"run_one_source upsert failed: {e}")

            # Write crawler_runs
            try:
                await asyncio.to_thread(
                    self._write_crawler_runs_for_source,
                    source_id, source.get("category", ""),
                    fetched_count, duration_ms, None,
                )
            except Exception as e:
                self.logger.warning(f"run_one_source crawler_runs write failed: {e}")

            return {
                "source_id": source_id,
                "fetched_count": fetched_count,
                "accepted_count": accepted_count,
                "duration_ms": duration_ms,
                "status": "success" if fetched_count > 0 else "partial",
                "error_msg": None,
            }
        except Exception as e:
            duration_ms = int((time.time() - start_ms) * 1000)
            error_msg = f"{type(e).__name__}: {str(e)[:200]}"
            self.logger.error(f"run_one_source {source_id} failed: {error_msg}")

            # Write crawler_runs with failure
            try:
                await asyncio.to_thread(
                    self._write_crawler_runs_for_source,
                    source_id, source.get("category", ""),
                    0, duration_ms, error_msg,
                )
            except Exception as e2:
                self.logger.warning(f"run_one_source crawler_runs write failed: {e2}")

            return {
                "source_id": source_id,
                "fetched_count": 0,
                "accepted_count": 0,
                "duration_ms": duration_ms,
                "status": "failed",
                "error_msg": error_msg,
            }

    async def _run_one_safe(self, category: Category, collector, since: str | None = None) -> CollectionResult:
        """跑单 collector，异常隔离

        Phase 9 招标源质量门禁：从 ``collector.last_source_results``
        读每源产出，填到 ``CollectionResult.source_results``。

        Phase 8: 起始时 INSERT 一行 collection_runs status='running',
        供 catchup_watchdog 检测孤儿. 结束时由 _write_collection_run
        UPDATE 同一行. INSERT 失败 → run_id=None (走老路径).

        P2-3: ``since`` 透传给 collector.collect 做时间窗口过滤。
        """
        start_ms = time.time()
        started_at = datetime.now(timezone.utc)
        # Phase 8: 起始插 'running' 行
        run_id = self._insert_running_row(category, started_at)
        try:
            items: list[HotspotItem] = await collector.collect(since=since)
            # Phase 8: dedup using simhash fingerprints
            items = await asyncio.to_thread(self._dedup_items, items)
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
            self.logger.error(f"{category.value} collector crashed: {e}")
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

    def _insert_running_row(self, category: Category, started_at) -> int | None:
        """Phase 8: 在 collection_runs 插一行 status='running', 供 watchdog 检测孤儿.

        Returns: 新行 id, 或 None (INSERT 失败时).
        """
        try:
            conn = get_connection()
            cur = conn.execute(
                """
                INSERT INTO collection_runs
                    (category, started_at, status, item_count, fallback_count)
                VALUES (?, ?, 'running', 0, 0)
                """,
                (category.value, started_at.isoformat()),
            )
            return int(cur.lastrowid)
        except Exception as e:
            # 迁移未跑 / DB lock / 其它错误 — 不阻塞采集
            self.logger.warning(
                f"insert running row for {category.value} failed: {e}"
            )
            return None

    def _dedup_items(self, items: list[HotspotItem]) -> list[HotspotItem]:
        """Deduplicate items using simhash fingerprints.

        For each item, compute a 64-bit simhash from ``title + summary``
        and compare against all existing fingerprints in the
        ``content_fingerprints`` table.  Items whose Hamming distance to
        an existing fingerprint is < 5 are considered duplicates and
        skipped.

        Non-duplicate items are written into ``content_fingerprints``
        immediately so that later items in the same batch see the
        updated fingerprint set (within-batch dedup).

        Parameters
        ----------
        items:
            Raw items returned by a collector, before DB upsert.

        Returns
        -------
        Filtered list with duplicates removed.
        """
        if not items:
            return items

        conn = get_connection()

        # Load existing fingerprints
        existing_rows = conn.execute(
            "SELECT hotspot_id, simhash FROM content_fingerprints"
        ).fetchall()
        # Convert from signed 64-bit (SQLite) to unsigned 64-bit (Python)
        existing = [
            (row[0], _from_signed_64(row[1]))
            for row in existing_rows
        ]

        # P1 性能: simhash 分桶索引 — 64-bit 指纹按 8×8-bit 块建桶。
        # Hamming 距离 < 5 (即 ≤4) 的两个指纹必然在 8 块中至少 4 块相同
        # (抽屉原理), 因此同桶候选集必包含全部真重复, 无需全表线性扫描。
        # 查找从 O(M) (全表) 降为 O(桶内候选数) ≈ O(1), 整体 O(N+M) 替代
        # O(N×M)。此为纯算法优化, 判定结果与全表扫描完全一致。
        _BUCKET_BITS = 8  # 每块 8 bit

        def _simhash_buckets(fp: int) -> list[int]:
            return [(fp >> (8 * i)) & 0xFF for i in range(8)]

        buckets: dict[int, list[tuple[str, int]]] = defaultdict(list)
        for eid, efp in existing:
            for b in set(_simhash_buckets(efp)):
                buckets[b].append((eid, efp))

        # Load existing canonical URLs for fast exact-match check
        existing_urls = {
            row[0]
            for row in conn.execute(
                "SELECT url_canonical FROM content_fingerprints"
            ).fetchall()
        }

        result: list[HotspotItem] = []
        for item in items:
            url_str = str(item.url)
            url_canonical = canonicalize_url(url_str)
            text = item.title
            if item.summary:
                text += " " + item.summary
            fp = simhash(text)

            # Fast path: exact URL match
            if url_canonical and url_canonical in existing_urls:
                self.logger.info(
                    f"Dedup skipped {item.id}: URL match {url_canonical}"
                )
                continue

            # Simhash Hamming distance check — 只比较同桶候选 (P1 分桶优化)
            duplicate = False
            candidates: set[tuple[str, int]] = set()
            for b in _simhash_buckets(fp):
                for cand in buckets.get(b, ()):
                    candidates.add(cand)
            for existing_id, existing_fp in candidates:
                if hamming_distance(fp, existing_fp) < 5:
                    self.logger.info(
                        f"Dedup skipped {item.id}: duplicate of {existing_id}"
                    )
                    duplicate = True
                    break

            if duplicate:
                continue

            # P0-5: 不在去重阶段写 content_fingerprints — hotspot 行此时尚不存在,
            # FK (hotspot_id REFERENCES hotspots(id)) 必失败, 指纹丢失导致跨轮去重失效。
            # 改为: 入库成功后由 _write_fingerprints 补写 (见 run_once/run_one 调用点)。

            # Update in-memory sets for within-batch dedup
            existing.append((item.id, fp))
            for b in set(_simhash_buckets(fp)):
                buckets[b].append((item.id, fp))
            if url_canonical:
                existing_urls.add(url_canonical)

            result.append(item)

        return result

    def _write_fingerprints(self, items: list[HotspotItem]) -> int:
        """P0-5: 入库成功后补写 content_fingerprints 指纹。

        必须在 hotspot 行已 upsert 之后调用 (content_fingerprints.hotspot_id
        有 FK REFERENCES hotspots(id)); 此前在 _dedup_items 内提前插入,
        新条目 hotspot 行不存在 → FK 失败被吞 → 指纹丢失 → 跨轮去重失效。
        现在改为入库后补写: FK 满足, 指纹首轮即落库, 同 URL 二次采集被拒。

        Returns: 实际写入的行数。
        """
        if not items:
            return 0
        conn = get_connection()
        written = 0
        try:
            for item in items:
                url_canonical = canonicalize_url(str(item.url))
                title_norm = normalize_title(item.title)
                text = item.title
                if item.summary:
                    text += " " + item.summary
                fp = simhash(text)
                cur = conn.execute(
                    """INSERT OR IGNORE INTO content_fingerprints
                       (hotspot_id, simhash, url_canonical, title_norm)
                       VALUES (?, ?, ?, ?)""",
                    (
                        item.id,
                        _to_signed_64(fp),
                        url_canonical or "",
                        title_norm or "",
                    ),
                )
                written += cur.rowcount
            conn.commit()
        except Exception as e:
            # 指纹补写失败不阻塞主流程 (去重是尽力而为, 下次采集会再判重)
            self.logger.warning(f"_write_fingerprints failed: {e}")
            return 0
        if written:
            self.logger.info(f"_write_fingerprints: {written} fingerprints written")
        return written

    def _write_raw_items(
        self, items: list[Any], results: list[CollectionResult]
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

        conn = get_connection()
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

                conn.execute(
                    """
                    INSERT INTO raw_items
                        (item_id, source_id, title, url, summary,
                         content_hash, published_at, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (item_id, source_id, title, url, summary,
                     content_hash, published_at),
                )
                written += 1
            except Exception:
                # 单条失败不阻塞整体
                continue

        self.logger.debug(f"raw_items written: {written}")

    def _write_bid_details(self, items: list[Any]) -> None:
        """Phase 1.3 (Crawler v2): 旁路写入 bid_details 表。

        从标讯类别 items 中提取结构化字段，写入 bid_details。
        只处理 category=bid 的条目，其他类别的条目跳过。
        不阻塞主流程，失败只打 warning。
        """
        bid_items = [it for it in items if getattr(it, "category", None) == Category.BID]
        if not bid_items:
            return

        repo = BidDetailRepo()
        batch: list[tuple[str, dict]] = []
        for it in bid_items:
            item_id = str(it.id) if hasattr(it, "id") else ""
            title = str(it.title) if hasattr(it, "title") else ""
            if not item_id or not title:
                continue

            fields = extract_bid_fields(title)
            # 补充 published_at
            published_at = (
                str(it.published_at) if hasattr(it, "published_at")
                and it.published_at else None
            )
            if published_at:
                fields["published_at"] = published_at

            batch.append((item_id, fields))

        if not batch:
            return

        written = repo.upsert_many(batch)
        self.logger.debug(f"bid_details written: {written}/{len(batch)}")

    def _write_crawler_runs(self, result: CollectionResult) -> None:
        """Phase 0 (Crawler v2): 旁路写入 crawler_runs 表。

        与 _write_collection_run 并行运行，记录每源每轮抓取统计。

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

            conn = get_connection()
            written = 0
            health_results: list[dict] = []
            for sr in source_results:
                source_name = sr.source_name
                status = "failed" if sr.error_msg else (
                    "partial" if sr.item_count == 0 else "success"
                )
                duration_ms = sr.duration_ms
                started_at = result.started_at.isoformat()
                finished_at = (
                    result.finished_at.isoformat()
                    if result.finished_at else ""
                )

                conn.execute(
                    """
                    INSERT INTO crawler_runs
                        (source_id, category, started_at, finished_at, status,
                         fetched_count, accepted_count, error_msg, duration_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (source_name, result.category.value,
                     started_at, finished_at, status,
                     sr.item_count, sr.item_count,
                     sr.error_msg or "", duration_ms),
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
                            "fetched_count": sr.item_count,
                            "accepted_count": sr.item_count,
                            "status": status,
                            "duration_ms": duration_ms,
                            "error_msg": sr.error_msg or "",
                        },
                    )
                    health_results.append(health)
                except Exception as e:
                    self.logger.debug(
                        f"apply_run_result skipped for {source_id}: {e}"
                    )

            if health_results:
                transitioned = [
                    h for h in health_results
                    if h.get("transition") not in ("none", "success_reset")
                    and "incremented" in h.get("transition", "")
                    or "to_" in h.get("transition", "")
                ]
                if transitioned:
                    self.logger.info(
                        f"crawler_runs: {len(transitioned)} source health transitions: "
                        + ", ".join(
                            f"{h['source_id']}→{h['new_status']}(f={h['consecutive_failures']})"
                            for h in transitioned[:5]
                        )
                    )
            self.logger.debug(f"crawler_runs written: {written}")
        except Exception as e:
            self.logger.warning(f"crawler_runs write skipped: {e}")

    def _write_crawler_runs_for_source(
        self,
        source_id: str,
        category: str,
        fetched_count: int,
        duration_ms: int,
        error_msg: str | None,
    ) -> None:
        """Write a single crawler_runs row for a source run."""
        now = datetime.now(timezone.utc).isoformat()
        status = "failed" if error_msg else (
            "partial" if fetched_count == 0 else "success"
        )
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO crawler_runs
                (source_id, category, started_at, finished_at, status,
                 fetched_count, accepted_count, error_msg, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id, category, now, now, status,
                fetched_count, fetched_count, error_msg or "", duration_ms,
            ),
        )

    def _write_collection_run(self, result: CollectionResult) -> None:
        """写入 collection_runs 表 (Phase 8: UPDATE 起始行, 老路径 fallback INSERT)"""
        try:
            conn = get_connection()
            status = CollectorStatus.FAILED if result.error else (
                CollectorStatus.PARTIAL if result.fallback_count > 0 else CollectorStatus.SUCCESS
            )
            finished_at_iso = (
                result.finished_at.isoformat() if result.finished_at else None
            )
            if result.run_id is not None:
                # Phase 8: UPDATE 起始 'running' 行
                conn.execute(
                    """
                    UPDATE collection_runs SET
                        finished_at = ?,
                        status = ?,
                        item_count = ?,
                        fallback_count = ?,
                        error_msg = ?
                    WHERE id = ?
                    """,
                    (
                        finished_at_iso,
                        status.value,
                        result.item_count,
                        result.fallback_count,
                        result.error,
                        int(result.run_id),
                    ),
                )
            else:
                # 老路径: 直接 INSERT (起始行 INSERT 失败时)
                conn.execute(
                    """INSERT INTO collection_runs
                    (category, started_at, finished_at, status, item_count, fallback_count, error_msg)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        result.category.value,
                        result.started_at.isoformat(),
                        finished_at_iso,
                        status.value,
                        result.item_count,
                        result.fallback_count,
                        result.error,
                    ),
                )
        except Exception as e:
            self.logger.error(f"write collection_run failed: {e}")


__all__ = ["CollectionService"]


def get_latest_run() -> dict[str, Any]:
    """Phase 39: 供 API 层读取最近一次 run_once 的产出。

    Returns
    -------
    dict with keys:
        ``count`` : int  本轮采集的 item 总数 (新插入 + 更新)
        ``at``    : Optional[datetime]  本轮 finished_at (tz-aware UTC)
    """
    # 返回拷贝避免外部修改
    return {
        "count": CollectionService._latest_run["count"],
        "at": CollectionService._latest_run["at"],
    }

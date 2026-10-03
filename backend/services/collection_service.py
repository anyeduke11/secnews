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
   ``collection_runs`` with a derived status (``SUCCESS`` / ``PARTIAL`` / ``FAILED``).

Batch 4 Task C: 本文件是编排 facade (run_once 主流程 + run_one/run_one_source
锁入口), 实现细节物理拆至 ``collection_dedup`` (simhash 去重 + 指纹)、
``collection_pipeline`` (旁路写入/富化/SSE 事件/单源单分类执行)、
``source_health_machine`` (独立模块, 经 pipeline.write_crawler_runs 触发)。

公开 API 逐字不变: ``CollectionService`` / ``get_latest_run``;
``_to_signed_64`` / ``_from_signed_64`` 为 re-export (t1_raw_to_refine / tests)。
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Any, ClassVar

from backend.collectors.ai_collector import AICollector
from backend.collectors.ai_security_collector import AISecurityCollector
from backend.collectors.arxiv_paper_collector import ArxivPaperCollector  # 2026-09-26 论文抓取
from backend.collectors.base import BaseCollector
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
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.logging_config import logger
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.trend_repo import TrendRepository
from backend.services.collection_dedup import (
    _from_signed_64,
    _to_signed_64,
    dedup_items,
    write_fingerprints,
)
from backend.services.collection_pipeline import (
    enrich_and_recheck,
    evaluate_source_coverage_logged,
    inject_custom_sources,
    invalidate_caches,
    publish_collect_done,
    rebuild_trend_and_log,
    run_category_locked,
    run_one_collector_safe,
    run_single_source,
    schedule_url_content_check,
    write_collection_run,
    write_crawler_runs,
    write_raw_items,
)


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
            # DEV-0178: Category.BID 采集链已随工作台聚焦裁决移除 (历史 bid 条目保留)
            Category.GITHUB: [GitHubCollector()],
            Category.TECH: [
                TechCollector(),  # Phase 25 P1
                HNCollector(),
                RedditCollector(),
                TelegramCollector(),
                OSSInsightCollector(),
            ],
            # 2026-09-26 论文抓取: category 扩展, 无独立 gate/job
            Category.PAPER: [ArxivPaperCollector()],
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
        self.logger.debug("collection started")  # P0-10: 例行心跳

        # Phase 8 Addendum 8.4: 注入 custom_sources (用户源优先, 追加不覆盖)
        inject_custom_sources(self.collectors, self.logger)

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

        # v1.9: 摘要富化 + P2-7 富化摘要复检 (尽力而为, 失败不阻塞主流程)
        if all_items:
            all_items = await enrich_and_recheck(all_items, self.logger)

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
                await asyncio.to_thread(write_fingerprints, all_items, self.logger)
            except Exception as e:
                self.logger.warning(f"fingerprint write skipped: {e}")

            # Phase 0 (Crawler v2): 旁路写入 raw_items（不阻塞主流程）
            # DEV-0178: bid_details 旁路写入已随标讯剔除移除 (bid 采集链下线)
            try:
                await asyncio.to_thread(write_raw_items, all_items, results, self.logger)
            except Exception as e:
                self.logger.warning(f"raw_items write skipped: {e}")

        # 重建趋势 — 同步 sqlite3 操作放 thread pool
        await rebuild_trend_and_log(self.trend, self.logger)

        # 写 collection_runs — Phase 9 修复：同步 DB 写，放 thread pool
        for r in results:
            await asyncio.to_thread(write_collection_run, r, self.logger)

        # Phase 0 (Crawler v2): 旁路写入 crawler_runs（不阻塞主流程）
        for r in results:
            try:
                await asyncio.to_thread(write_crawler_runs, r, self.logger)
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

        invalidate_caches(self.logger)
        schedule_url_content_check(self.logger)
        publish_collect_done(results, total, duration_ms, self.logger)

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

        # Phase 9 招标源质量门禁：评估每源产出 + 覆盖度
        await evaluate_source_coverage_logged(report, self.logger)

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
        """单分类执行 (持锁路径) — 实现见 collection_pipeline.run_category_locked。"""
        return await run_category_locked(
            category,
            since=since,
            collectors=self.collectors,
            repo=self.repo,
            trend=self.trend,
            logger=self.logger,
        )

    async def run_one_source(self, source_id: str) -> dict:
        """Run collection for a single source by its crawler_sources ID.

        P2-1: 与 run_once 共用 self._lock (防并发写与共享状态覆盖)。

        Returns a dict with: source_id, fetched_count, accepted_count,
        duration_ms, status ('success'|'failed'), error_msg
        """
        async with self._lock:
            return await run_single_source(source_id, self.collectors, self.logger)

    async def _run_one_safe(self, category: Category, collector, since: str | None = None) -> CollectionResult:
        """跑单 collector，异常隔离 (实现见 collection_pipeline.run_one_collector_safe)。"""
        return await run_one_collector_safe(
            category, collector, since=since, logger=self.logger
        )

    # --- 测试接缝保留: 历史测试经实例调用/patch 这三个私有写入路径 ---

    def _dedup_items(self, items: list[HotspotItem]) -> list[HotspotItem]:
        return dedup_items(items, self.logger)

    def _write_fingerprints(self, items: list[HotspotItem]) -> int:
        return write_fingerprints(items, self.logger)

    def _write_crawler_runs(self, result: CollectionResult) -> None:
        write_crawler_runs(result, self.logger)


# re-export: _to/_from_signed_64 消费方为 t1_raw_to_refine 与 tests
__all__ = [
    "CollectionService",
    "_from_signed_64",
    "_to_signed_64",
]


def get_latest_run() -> dict[str, Any]:
    """Phase 39: 供 API 层读取最近一次 run_once 的产出。

    Returns: dict with ``count`` (本轮采集 item 总数) 与
    ``at`` (Optional[datetime], tz-aware UTC)。返回拷贝避免外部修改。
    """
    return {
        "count": CollectionService._latest_run["count"],
        "at": CollectionService._latest_run["at"],
    }

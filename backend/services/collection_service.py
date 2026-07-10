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
import time
from datetime import datetime, timezone

from backend.collectors.ai_collector import AICollector
from backend.collectors.base import BaseCollector
from backend.collectors.bid_collector import BidCollector
from backend.collectors.finance_collector import FinanceCollector
from backend.collectors.github_collector import GitHubCollector
from backend.collectors.security_collector import SecurityCollector
from backend.collectors.startup_collector import StartupCollector
from backend.collectors.tech_collector import TechCollector  # Phase 25 P1
from backend.cache import invalidate as cache_invalidate
from backend.domain.collection import CollectionReport, CollectionResult
from backend.domain.enums import Category, CollectorStatus
from backend.domain.models import HotspotItem
from backend.logging_config import logger
from backend.repository.custom_source_repo import CustomSourceRepository
from backend.repository.db import get_connection
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.trend_repo import TrendRepository


class CollectionService:
    """统一编排所有 collector"""

    # Phase 39: 模块级变量, 跟踪最近一次 run_once 的产出
    # (key reasons: 1) 避免每次新 CollectionService 实例的 state 丢失;
    #                2) 跨请求可读, 不需要注入到 HotspotService)
    # 用 dict 包装避免 global 关键字
    _latest_run: dict[str, Any] = {"count": 0, "at": None}

    def __init__(self):
        self.collectors: dict[Category, BaseCollector] = {
            Category.AI: AICollector(),
            Category.SECURITY: SecurityCollector(),
            Category.FINANCE: FinanceCollector(),
            Category.STARTUP: StartupCollector(),
            Category.BID: BidCollector(),
            Category.GITHUB: GitHubCollector(),
            Category.TECH: TechCollector(),  # Phase 25 P1
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
            for cat, c in self.collectors.items():
                extra = custom_repo.list_enabled_by_category(cat)
                if extra:
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

        tasks = {
            cat: asyncio.create_task(self._run_one_safe(cat, c))
            for cat, c in self.collectors.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=False)

        # 合并所有 items
        all_items: list[HotspotItem] = []
        for r in results:
            all_items.extend(r.items)

        # 写 DB — Phase 9 修复：放到 thread pool 避免阻塞 event loop
        if all_items:
            try:
                upserted = await asyncio.to_thread(self.repo.upsert_many, all_items)
                self.logger.info(f"upserted {upserted} items")
            except Exception as e:
                self.logger.error(f"upsert failed: {e}")
                # 不中断，写入 collection_runs 失败状态

        # 重建趋势 — Phase 9 修复：trend.rebuild 是同步 sqlite3 操作，放 thread pool
        try:
            trend_count = await asyncio.to_thread(self.trend.rebuild, 24)
            self.logger.info(f"trend rebuilt: {trend_count} points")
        except Exception as e:
            self.logger.error(f"trend rebuild failed: {e}")

        # 写 collection_runs — Phase 9 修复：同步 DB 写，放 thread pool
        for r in results:
            await asyncio.to_thread(self._write_collection_run, r)

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
                loop.create_task(run_url_content_check())
        except Exception as e:
            self.logger.warning(f"schedule url_content_check failed: {e}")

        # 统计
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((time.time() - start_ms) * 1000)
        total = sum(r.item_count for r in results)
        fallback = sum(r.fallback_count for r in results)
        failures = [
            {"category": r.category.value, "error": r.error}
            for r in results if r.error
        ]

        report = CollectionReport(
            total=total,
            success_count=sum(1 for r in results if not r.error),
            failed_count=sum(1 for r in results if r.error),
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

    async def run_one(self, category: Category) -> CollectionReport:
        """单分类执行（手动触发 / 重试）"""
        started_at = datetime.now(timezone.utc)
        start_ms = time.time()

        if category not in self.collectors:
            raise ValueError(f"unknown category: {category}")

        c = self.collectors[category]
        result = await self._run_one_safe(category, c)

        if result.items:
            try:
                await asyncio.to_thread(self.repo.upsert_many, result.items)
            except Exception as e:
                self.logger.error(f"upsert failed: {e}")
                result.error = f"upsert failed: {e}"

        try:
            await asyncio.to_thread(self.trend.rebuild, 24)
        except Exception as e:
            self.logger.error(f"trend rebuild failed: {e}")

        await asyncio.to_thread(self._write_collection_run, result)

        # Phase 4: 单分类采集后也失效缓存
        try:
            cache_invalidate("hotspots:*")
            cache_invalidate("trends:*")
        except Exception as e:
            self.logger.warning(f"cache invalidation failed: {e}")

        finished_at = datetime.now(timezone.utc)
        duration_ms = int((time.time() - start_ms) * 1000)
        report = CollectionReport(
            total=result.item_count,
            success_count=0 if result.error else 1,
            failed_count=1 if result.error else 0,
            fallback_count=result.fallback_count,
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=finished_at,
            failures=[{"category": category.value, "error": result.error}] if result.error else [],
            results=[result],
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

    async def _run_one_safe(self, category: Category, collector) -> CollectionResult:
        """跑单 collector，异常隔离

        Phase 9 招标源质量门禁：从 ``collector.last_source_results``
        读每源产出，填到 ``CollectionResult.source_results``。
        """
        start_ms = time.time()
        started_at = datetime.now(timezone.utc)
        try:
            items: list[HotspotItem] = await collector.collect()
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
                error=f"{type(e).__name__}: {str(e)[:200]}",
            )

    def _write_collection_run(self, result: CollectionResult) -> None:
        """写入 collection_runs 表"""
        try:
            conn = get_connection()
            status = CollectorStatus.FAILED if result.error else (
                CollectorStatus.PARTIAL if result.fallback_count > 0 else CollectorStatus.SUCCESS
            )
            conn.execute(
                """INSERT INTO collection_runs
                (category, started_at, finished_at, status, item_count, fallback_count, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.category.value,
                    result.started_at.isoformat(),
                    result.finished_at.isoformat() if result.finished_at else None,
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

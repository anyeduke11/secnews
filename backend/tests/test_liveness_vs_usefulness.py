"""cadence 修正批 — 存活 (liveness) 与有用 (usefulness) 分离回归.

第一性根因: 健康机 / 覆盖统计此前只看 ``item_count`` (相关性 + 质量过滤 **之后**
的条目数)。招标源首页实测 40 条锚点 / 0 条安全相关 (含当时 "存活" 的采招网),
0 条 = 业务上"今天没有相关招标", 却被当成 "源死了" → 62 个招标源被判 dead。

修复: ``SourceResult.raw_count`` (过滤前候选数) + ``fetched_count`` 属性 (max),
健康机 / crawler_runs.fetched_count / source_stats.produced 用存活口径,
``item_count`` / accepted_count / total_items 保留有用口径。

覆盖:
- ``SourceResult.fetched_count`` 语义 + 向后兼容 (未接线路径 raw=0)
- ``CollectionService._write_crawler_runs``: fetched/accepted 分列, 健康机看 fetched
- ``CollectionService.run_one_source``: 从 collector.last_source_results 取 raw
- ``SourceStatsRepository.upsert_after_run(produced=...)``: 显式存活判定, total_items 仍累加有用数
- ``evaluate_source_coverage``: 40/0 的源计入 active 而非 zero
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.domain.collection import CollectionReport, CollectionResult, SourceResult
from backend.domain.enums import Category


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# SourceResult.fetched_count
# ---------------------------------------------------------------------------
def test_fetched_count_prefers_raw_and_falls_back_to_items():
    assert SourceResult(source_name="a", source_url="u", raw_count=40, item_count=0).fetched_count == 40
    assert SourceResult(source_name="a", source_url="u", raw_count=0, item_count=3).fetched_count == 3
    assert SourceResult(source_name="a", source_url="u").fetched_count == 0
    # items ⊆ raw 是常态, 但防御性取 max
    assert SourceResult(source_name="a", source_url="u", raw_count=2, item_count=5).fetched_count == 5


# ---------------------------------------------------------------------------
# DB 侧 (temp_db: 全 migration, crawler_sources + crawler_runs + source_stats)
# ---------------------------------------------------------------------------
def _insert_source(conn, sid: str, name: str, category: str = "bid", status: str = "active"):
    conn.execute(
        "INSERT INTO crawler_sources (id, category, name, kind, url, priority, enabled, status, consecutive_failures) VALUES (?, ?, ?, 'html', 'https://example.com/', 50, 1, ?, 0)",
        (sid, category, name, status),
    )
    conn.commit()


@pytest.fixture
def svc(temp_db):
    from backend.services.collection_service import CollectionService

    return CollectionService()


def _result(name: str, raw: int, items: int) -> CollectionResult:
    return CollectionResult(
        category=Category.BID,
        started_at=_now(),
        finished_at=_now(),
        source_results=[SourceResult(source_name=name, source_url="https://example.com/", raw_count=raw, item_count=items)],
    )


def test_write_crawler_runs_splits_fetched_and_accepted_and_keeps_source_active(svc):
    from backend.repository.db import get_connection

    conn = get_connection()
    _insert_source(conn, "bid:采招网", "采招网")

    svc._write_crawler_runs(_result("采招网", raw=40, items=0))

    run = conn.execute(
        "SELECT status, fetched_count, accepted_count FROM crawler_runs WHERE source_id = '采招网' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert (run["fetched_count"], run["accepted_count"]) == (40, 0)
    assert run["status"] == "partial"  # 有用口径: 0 条相关 → partial (不是 failed)

    src = conn.execute("SELECT status, consecutive_failures FROM crawler_sources WHERE id = 'bid:采招网'").fetchone()
    assert src["status"] == "active", "40 条锚点 / 0 条相关的源必须保持 active"
    assert src["consecutive_failures"] == 0


def test_write_crawler_runs_zero_raw_still_counts_as_failure_for_health(svc):
    from backend.repository.db import get_connection

    conn = get_connection()
    _insert_source(conn, "bid:空页", "空页")
    for _ in range(3):
        svc._write_crawler_runs(_result("空页", raw=0, items=0))
    src = conn.execute("SELECT status, consecutive_failures FROM crawler_sources WHERE id = 'bid:空页'").fetchone()
    assert src["consecutive_failures"] == 3
    assert src["status"] == "stale", "真正 0 候选连续 3 轮 → stale (存活口径未放水)"


@pytest.mark.asyncio
async def test_run_one_source_reads_raw_from_last_source_results(svc, monkeypatch):
    from backend.repository.db import get_connection

    conn = get_connection()
    _insert_source(conn, "bid:千里马招标网", "千里马招标网")

    class _Fake:
        sources = [{"name": "千里马招标网", "url": "https://example.com/"}]
        last_source_results: list = []

        async def collect(self, only_source=None, since=None):
            self.last_source_results = [
                SourceResult(source_name="千里马招标网", source_url="https://example.com/", raw_count=40, item_count=0)
            ]
            return []

    monkeypatch.setitem(svc.collectors, Category.BID, [_Fake()])
    out = await svc.run_one_source("bid:千里马招标网")
    assert (out["fetched_count"], out["accepted_count"], out["status"]) == (40, 0, "partial")
    run = conn.execute(
        "SELECT fetched_count, accepted_count, status FROM crawler_runs WHERE source_id = 'bid:千里马招标网' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert (run["fetched_count"], run["accepted_count"], run["status"]) == (40, 0, "partial")


def test_upsert_after_run_produced_override_keeps_active_and_items_metric(temp_db):
    from backend.repository.source_stats_repo import SourceStatsRepository

    repo = SourceStatsRepository()
    for _ in range(8):  # 远超 dead_threshold=6
        repo.upsert_after_run("bid", "中国政府采购网", "https://example.com/", 0, None, produced=True)
    row = repo.get_one("bid", "中国政府采购网")
    assert row["status"] == "active"
    assert int(row["zero_yield_runs"]) == 0
    assert int(row["total_items"]) == 0, "total_items 是有用口径, 不因存活判定而虚增"
    assert row["last_seen_at"] is not None

    # 未传 produced → 旧语义 (item_count>=1 才算产出)
    for _ in range(3):
        repo.upsert_after_run("bid", "老口径源", "https://example.com/", 0, None)
    assert int(repo.get_one("bid", "老口径源")["zero_yield_runs"]) == 3


def test_evaluate_source_coverage_counts_raw_only_source_as_active(temp_db):
    from backend.quality.source_coverage import evaluate_source_coverage

    report = CollectionReport(
        results=[
            CollectionResult(
                category=Category.BID,
                started_at=_now(),
                finished_at=_now(),
                source_results=[
                    SourceResult(source_name="有锚点无相关", source_url="https://example.com/a", raw_count=40, item_count=0),
                    SourceResult(source_name="真空页", source_url="https://example.com/b", raw_count=0, item_count=0),
                    SourceResult(source_name="有产出", source_url="https://example.com/c", raw_count=12, item_count=3),
                ],
            )
        ],
        total=3,
        started_at=_now(),
        finished_at=_now(),
    )
    cov = evaluate_source_coverage(report)
    cat = next(c for c in cov.categories if c.category == "bid")
    assert cat.active_sources == 2, cat
    assert cat.zero_sources == 1, cat

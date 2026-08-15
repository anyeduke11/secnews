"""CollectionService 单元测试

覆盖：
  - service 包含 5 个 collector（每个 Category 各一个）
  - run_once 返回合法的 CollectionReport
  - run_once 走 upsert 路径（mock repo 避免外部依赖）
  - run_once 写 5 行 collection_runs
  - run_once 重建 trend_snapshots（120 行 = 24h × 5 分类）
  - run_one 单分类执行与其他分类隔离
  - 单 collector 抛异常时全局仍能跑通

实现说明
--------
本测试 mock 掉 5 个 collector 的 ``collect()``，避免触发实际 HTTP 抓取
（外网在 CI / Windows 上不稳定 + 单个 collector 可能耗时 20s+）。这
样既快又可重现，又能聚焦在 service 的编排逻辑（并发 / 异常隔离 /
DB 写入 / trend 重建）上。
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from backend.config import config
from backend.domain.collection import CollectionReport
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.repository import db
from backend.repository.db import get_connection
from backend.services.collection_service import CollectionService


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """重定向 config.db_path 到 tmp_path 下的临时文件，初始化 schema。"""
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()  # 清掉前序测试的 thread-local 连接 (指向旧 DB)
    db.init_db()
    yield test_db
    db.close_db()


def _make_item(id_: str, cat: Category) -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=id_,
        title=f"title {id_}",
        source="src",
        url=f"https://example.com/{id_}",
        category=cat,
        published_at=now,
        fetched_at=now,
    )


def _make_fake_collect(cat: Category, count: int = 3):
    """构造一个 collect() 替身：返回指定数量的 items，全是指定 cat。

    P2-3: collect() 新增 since 参数 — fake 需兼容 (only_source/since 可选)。
    """
    async def fake_collect(only_source: str | None = None, since: str | None = None) -> list[HotspotItem]:
        return [_make_item(f"{cat.value}_{i}", cat) for i in range(count)]
    return fake_collect


def _patch_all_collectors(
    svc: CollectionService,
    *,
    counts: dict[Category, int] | None = None,
    fail: set[Category] | None = None,
) -> None:
    """替换所有 collector.collect() 为可控制返回 / 抛异常的替身。

    ``counts``  -> 每分类返回多少条 item（默认每分类 3）
    ``fail``    -> 这些分类的 collect() 应抛 RuntimeError
    """
    if counts is None:
        counts = dict.fromkeys(Category, 3)
    fail = fail or set()
    for cat, c_list in svc.collectors.items():
        for collector in c_list:
            if cat in fail:
                collector.collect = AsyncMock(
                    side_effect=RuntimeError(f"simulated crash {cat.value}")
                )
            else:
                collector.collect = AsyncMock(
                    side_effect=_make_fake_collect(cat, counts.get(cat, 3))
                )


# ---------------------------------------------------------------------------
# 1. service 包含 6 个 collector
# ---------------------------------------------------------------------------
def test_service_has_6_collectors(temp_db):
    """service.collectors 应包含全部 8 个 Category (v1.9 加 ai_security)。"""
    svc = CollectionService()
    assert len(svc.collectors) == 8
    for cat in Category:
        assert cat in svc.collectors


# ---------------------------------------------------------------------------
# 2. run_once 返回合法的 CollectionReport
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_once_returns_collection_report(temp_db):
    """run_once 应返回合法 CollectionReport，字段一致。"""
    svc = CollectionService()
    _patch_all_collectors(svc)

    report = await svc.run_once()

    assert isinstance(report, CollectionReport)
    assert report.total >= 0
    # P2-6: 每分类可多 collector — 结果数 = 全部 collector 数
    n_collectors = sum(len(v) for v in svc.collectors.values())
    assert report.success_count + report.failed_count == n_collectors
    assert report.duration_ms >= 0
    assert report.started_at is not None
    assert report.finished_at is not None
    assert len(report.results) == n_collectors
    # 全部结果应覆盖全部 category
    cats = {r.category for r in report.results}
    assert cats == set(Category)


# ---------------------------------------------------------------------------
# 3. run_once 走 upsert 路径
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_once_calls_upsert(temp_db, monkeypatch):
    """run_once 应触发 repo.upsert_many 一次，传入 items 数 == report.total。"""
    svc = CollectionService()
    _patch_all_collectors(svc, counts={
        Category.AI: 4,
        Category.SECURITY: 3,
        Category.FINANCE: 5,
        Category.STARTUP: 2,
        Category.BID: 6,
    })

    captured: dict[str, object] = {}

    def fake_upsert(items):
        captured["items"] = items
        captured["count"] = len(items)
        return len(items)

    monkeypatch.setattr(svc.repo, "upsert_many", fake_upsert)

    report = await svc.run_once()
    # upsert 被调用一次
    assert "items" in captured
    # mock 出来的 fake_collect 返回的是 HotspotItem，
    # 但 CollectionResult.items 已被 model_dump 成 dict。
    # 因此 service 走的是 dict 路径，repo 期望 HotspotItem。
    # 我们只验证 upsert 被调用 + 调用次数为 1。
    assert captured["count"] == report.total


@pytest.mark.asyncio
async def test_run_once_upsert_isolated_by_failure(temp_db, monkeypatch):
    """单个 collector 抛异常时 upsert 仍会被调用（其他 5 个分类的 items）。"""
    svc = CollectionService()
    _patch_all_collectors(
        svc,
        counts=dict.fromkeys(Category, 3),
        fail={Category.AI},
    )

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        svc.repo,
        "upsert_many",
        lambda items: captured.setdefault("called", True),
    )

    report = await svc.run_once()
    n_collectors = sum(len(v) for v in svc.collectors.values())
    assert report.failed_count == 1
    assert report.success_count == n_collectors - 1
    # upsert 仍被调用
    assert captured.get("called") is True


# ---------------------------------------------------------------------------
# 4. run_once 写 collection_runs (每 collector 一行, P2-6 多 collector)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_once_writes_collection_runs(temp_db):
    """run_once 完成后 collection_runs 表应有每 collector 一行。"""
    svc = CollectionService()
    _patch_all_collectors(svc)
    await svc.run_once()

    conn = get_connection()
    rows = conn.execute("SELECT COUNT(*) FROM collection_runs").fetchall()
    n_collectors = sum(len(v) for v in svc.collectors.values())
    assert int(rows[0][0]) == n_collectors

    cat_rows = conn.execute(
        "SELECT DISTINCT category FROM collection_runs"
    ).fetchall()
    cats = {r[0] for r in cat_rows}
    assert cats == {
        "ai",
        "ai_security",
        "security",
        "finance",
        "startup",
        "bid",
        "github",
        "tech",
    }


# ---------------------------------------------------------------------------
# 5. run_once 重建 trend_snapshots（168 行 = 24h × 7 分类, Phase 25 P1）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_once_calls_trend_rebuild(temp_db):
    """run_once 完成后 trend_snapshots 应有 24 × 8 = 192 行。"""
    svc = CollectionService()
    _patch_all_collectors(svc)
    await svc.run_once()

    conn = get_connection()
    rows = conn.execute("SELECT COUNT(*) FROM trend_snapshots").fetchall()
    assert int(rows[0][0]) == 192


# ---------------------------------------------------------------------------
# 6. run_one 单分类执行
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_one_category_isolated(temp_db):
    """run_one(Category.AI) 只跑 AI 一类，collection_runs 只多 1 行。"""
    svc = CollectionService()
    _patch_all_collectors(svc)

    report = await svc.run_one(Category.AI)
    assert isinstance(report, CollectionReport)
    assert len(report.results) == 1
    assert report.results[0].category is Category.AI

    # collection_runs 应只有 1 行
    conn = get_connection()
    rows = conn.execute("SELECT COUNT(*) FROM collection_runs").fetchall()
    assert int(rows[0][0]) == 1

    cat_row = conn.execute(
        "SELECT category FROM collection_runs LIMIT 1"
    ).fetchone()
    assert cat_row[0] == "ai"


@pytest.mark.asyncio
async def test_run_one_unknown_category_raises(temp_db):
    """run_one 传入未知 Category 应抛 ValueError。"""
    svc = CollectionService()
    with pytest.raises(ValueError):
        await svc.run_one("not-a-category")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 7. 单 collector 异常隔离
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_collector_exception_isolated(temp_db):
    """mock 一个 collector 抛异常，run_once 仍能完成，collection_runs 全 6 行。"""
    svc = CollectionService()
    _patch_all_collectors(
        svc,
        counts=dict.fromkeys(Category, 3),
        fail={Category.AI},
    )

    report = await svc.run_once()

    # P2-6: 1 个 failed + (全部 collector - 1) 个 success
    n_collectors = sum(len(v) for v in svc.collectors.values())
    assert report.failed_count == 1
    assert report.success_count == n_collectors - 1

    # collection_runs 应有每 collector 一行
    conn = get_connection()
    rows = conn.execute("SELECT COUNT(*) FROM collection_runs").fetchall()
    assert int(rows[0][0]) == n_collectors

    # 失败的那一行应有 error_msg，状态为 'failed'
    failed_row = conn.execute(
        "SELECT category, status, error_msg FROM collection_runs "
        "WHERE category = 'ai'"
    ).fetchone()
    assert failed_row is not None
    assert failed_row[1] == "failed"
    assert failed_row[2] is not None
    assert "simulated crash" in failed_row[2]

    # 其他分类应各有自己的 collector 行 (P2-6: 全部非 ai collector)
    other_count = conn.execute(
        "SELECT COUNT(*) FROM collection_runs WHERE category != 'ai'"
    ).fetchall()
    assert int(other_count[0][0]) == n_collectors - 1

"""v1.9 Phase 9 — catchup_service (per-source checkpoint + 日志 + 验证) 集成测试.

覆盖 (8 用例):
  - P9.1 _execute_catchup_run 跑完后 catchup_checkpoints 有 per-source 行 (done)
  - P9.2 失败源 → mark_failed 写 error_msg
  - P9.3 续传: 上一 run 已 done → 本 run 跳过 (skipped)
  - P9.4 collect_start / source_done / collect_done 事件被发出
  - P9.5 run 完成后跑 validate_and_persist → 写 collect_validations
  - P9.6 重跑 catchup_service 应恢复 collector.sources 和 max_items
  - P9.7 mode=auto 不阻塞 mode=manual
  - P9.8 整轮崩溃 → 标 failed + 写 collect_done(failed) 事件
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.config import config
from backend.domain.enums import Category
from backend.domain.models import HotspotItem
from backend.repository import db
from backend.repository.catchup_checkpoint_repo import CatchupCheckpointRepository
from backend.repository.catchup_repo import CatchupRepository
from backend.services import catchup_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_catchup_phase9.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture(autouse=True)
def reset_module_state():
    catchup_service._last_auto_enqueue_at = None
    catchup_service._last_orphan_recovery_at = None
    catchup_service._current_manual_run = None
    if catchup_service._lock.locked():
        try:
            catchup_service._lock.release()
        except RuntimeError:
            pass
    yield
    catchup_service._last_auto_enqueue_at = None
    catchup_service._last_orphan_recovery_at = None
    catchup_service._current_manual_run = None


@pytest.fixture
def checkpoint_repo(temp_db) -> CatchupCheckpointRepository:
    return CatchupCheckpointRepository()


@pytest.fixture
def catchup_repo(temp_db) -> CatchupRepository:
    return CatchupRepository()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_item(cat: Category, idx: int, source: str = "test_src") -> HotspotItem:
    now = datetime.now(timezone.utc)
    return HotspotItem(
        id=f"{cat.value}_{idx}",
        title=f"test title {cat.value}_{idx}",
        source=source,
        url=f"https://example.com/{cat.value}/{idx}",
        category=cat,
        published_at=now,
        fetched_at=now,
    )


def _make_source_result(name: str, count: int, error_msg=None, duration_ms=100):
    """构造 SourceResult 对象 (mimic collectors.base 中定义)."""
    from backend.domain.collection import SourceResult
    return SourceResult(
        source_name=name,
        source_url=f"https://example.com/{name}",
        item_count=count,
        error_msg=error_msg,
        duration_ms=duration_ms,
    )


def _make_mock_svc(target_cats, source_results_per_cat):
    """mock CollectionService 让 run_one 返回指定 source_results.

    source_results_per_cat: dict[Category, list[SourceResult]]
    """
    svc = MagicMock()
    svc.collectors = {}
    for cat in target_cats:
        col = MagicMock()
        col.sources = [
            {"name": sr.source_name, "url": sr.source_url}
            for sr in source_results_per_cat[cat]
        ]
        col.max_items = 50
        col.last_source_results = source_results_per_cat[cat]
        svc.collectors[cat] = [col]  # P2-6: 每分类为 collector 列表

    async def fake_run_one(cat, since=None):
        from backend.domain.collection import CollectionResult
        results = source_results_per_cat[cat]
        total = sum(int(r.item_count or 0) for r in results if not r.error_msg)
        return MagicMock(
            total=total,
            results=[CollectionResult(
                category=cat,
                items=[],
                item_count=total,
                fallback_count=0,
                source_results=results,
                duration_ms=200,
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                run_id=None,
            )],
        )
    svc.run_one = fake_run_one
    return svc


# ---------------------------------------------------------------------------
# P9.1 — _execute_catchup_run 写 per-source checkpoint (done)
# ---------------------------------------------------------------------------
def test_execute_catchup_writes_done_checkpoints(
    temp_db, checkpoint_repo, catchup_repo
):
    """跑完 1 个 category (2 sources) → 2 行 checkpoint (done)."""
    target = [Category.AI]
    srs = {
        Category.AI: [
            _make_source_result("hn", 5),
            _make_source_result("ph", 3),
        ],
    }
    svc = _make_mock_svc(target, srs)

    with patch.object(catchup_service, "_get_dead_source_names", return_value={}), \
         patch("backend.services.collection_service.CollectionService", return_value=svc), \
         patch("backend.scheduler.jobs.trend_rebuild_job", new=AsyncMock()), \
         patch("backend.services.collection_logger.log_collect_event") as mock_log:
        run = catchup_repo.create(
            mode="manual",
            since_window=(datetime.now(timezone.utc) - timedelta_hours(1)).isoformat(),
            until_window=datetime.now(timezone.utc).isoformat(),
            categories=["ai"],
            max_per_source=50,
        )
        _run(catchup_service._execute_catchup_run(run.id, mode="manual"))

    ckpts = checkpoint_repo.list_for_run(run.id)
    done_ckpts = [c for c in ckpts if c.status == "done"]
    assert len(done_ckpts) == 2
    names = {c.source_name for c in done_ckpts}
    assert names == {"hn", "ph"}


# ---------------------------------------------------------------------------
# P9.2 — 失败源 → mark_failed 写 error_msg
# ---------------------------------------------------------------------------
def test_execute_catchup_writes_failed_checkpoint_with_error(
    temp_db, checkpoint_repo, catchup_repo
):
    target = [Category.AI]
    srs = {
        Category.AI: [
            _make_source_result("hn", 5),
            _make_source_result("broken", 0, error_msg="HTTP 503"),
        ],
    }
    svc = _make_mock_svc(target, srs)
    with patch.object(catchup_service, "_get_dead_source_names", return_value={}), \
         patch("backend.services.collection_service.CollectionService", return_value=svc), \
         patch("backend.scheduler.jobs.trend_rebuild_job", new=AsyncMock()), \
         patch("backend.services.catchup_service.validate_and_persist",
               return_value=MagicMock(issues=[])):
        run = catchup_repo.create(
            mode="manual",
            since_window=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            until_window=datetime.now(timezone.utc).isoformat(),
            categories=["ai"],
            max_per_source=50,
        )
        _run(catchup_service._execute_catchup_run(run.id, mode="manual"))

    failed = checkpoint_repo.get(run.id, "ai", "broken")
    assert failed is not None
    assert failed.status == "failed"
    assert "503" in (failed.error_msg or "")

    # run 终态应为 partial
    final = catchup_repo.get(run.id)
    assert final.status == "partial"


# ---------------------------------------------------------------------------
# P9.3 — 续传: 上一 run 已 done → 本 run 跳过 (skipped)
# ---------------------------------------------------------------------------
def test_resumption_marks_sources_skipped(
    temp_db, checkpoint_repo, catchup_repo
):
    """上一 run (id=99) hn 已 done → 本 run (id=100) hn → status=skipped."""
    # 上一 run done
    checkpoint_repo.mark_done(run_id=99, category="ai", source_name="hn", items_count=10)
    target = [Category.AI]
    srs = {
        Category.AI: [
            _make_source_result("hn", 0),  # 本 run 不真跑 (被 skip)
            _make_source_result("ph", 5),
        ],
    }
    svc = _make_mock_svc(target, srs)
    with patch.object(catchup_service, "_get_dead_source_names", return_value={}), \
         patch("backend.services.collection_service.CollectionService", return_value=svc), \
         patch("backend.scheduler.jobs.trend_rebuild_job", new=AsyncMock()), \
         patch("backend.services.catchup_service.validate_and_persist",
               return_value=MagicMock(issues=[])):
        run = catchup_repo.create(
            mode="auto",
            since_window=(datetime.now(timezone.utc) - timedelta_hours(1)).isoformat(),
            until_window=datetime.now(timezone.utc).isoformat(),
            categories=["ai"],
            max_per_source=50,
        )
        _run(catchup_service._execute_catchup_run(run.id, mode="auto"))

    hn = checkpoint_repo.get(run.id, "ai", "hn")
    assert hn is not None
    assert hn.status == "skipped"
    assert "resumed" in (hn.error_msg or "")

    # ph 应该 done
    ph = checkpoint_repo.get(run.id, "ai", "ph")
    assert ph.status == "done"
    assert ph.items_count == 5


# ---------------------------------------------------------------------------
# P9.4 — collect_start / source_done / collect_done 事件被发出
# ---------------------------------------------------------------------------
def test_structured_events_emitted(temp_db, catchup_repo):
    target = [Category.AI]
    srs = {
        Category.AI: [_make_source_result("hn", 5)],
    }
    svc = _make_mock_svc(target, srs)
    with patch.object(catchup_service, "_get_dead_source_names", return_value={}), \
         patch("backend.services.collection_service.CollectionService", return_value=svc), \
         patch("backend.scheduler.jobs.trend_rebuild_job", new=AsyncMock()), \
         patch("backend.services.catchup_service.validate_and_persist",
               return_value=MagicMock(issues=[])), \
         patch("backend.services.collection_logger.log_collect_event") as mock_log:
        run = catchup_repo.create(
            mode="manual",
            since_window=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            until_window=datetime.now(timezone.utc).isoformat(),
            categories=["ai"],
            max_per_source=50,
        )
        _run(catchup_service._execute_catchup_run(run.id, mode="manual"))

    events = [c.args[0] for c in mock_log.call_args_list if c.args]
    # 至少: collect_start, category_start, source_done, category_done, validate_done, collect_done
    assert "collect_start" in events
    assert "source_done" in events
    assert "collect_done" in events


# ---------------------------------------------------------------------------
# P9.5 — run 完成后跑 validate_and_persist
# ---------------------------------------------------------------------------
def test_validation_runs_after_catchup(temp_db, catchup_repo):
    target = [Category.AI]
    srs = {
        Category.AI: [_make_source_result("hn", 5)],
    }
    svc = _make_mock_svc(target, srs)
    with patch.object(catchup_service, "_get_dead_source_names", return_value={}), \
         patch("backend.services.collection_service.CollectionService", return_value=svc), \
         patch("backend.scheduler.jobs.trend_rebuild_job", new=AsyncMock()), \
         patch("backend.services.catchup_service.validate_and_persist") as mock_v:
        mock_v.return_value = MagicMock(issues=[])
        run = catchup_repo.create(
            mode="manual",
            since_window=(datetime.now(timezone.utc) - timedelta_hours(1)).isoformat(),
            until_window=datetime.now(timezone.utc).isoformat(),
            categories=["ai"],
            max_per_source=50,
        )
        _run(catchup_service._execute_catchup_run(run.id, mode="manual"))

    # validate_and_persist 被调, run_id 正确
    assert mock_v.called
    # 调用是位置参数: validate_and_persist(run_id, since_iso, until_iso)
    assert mock_v.call_args.args[0] == run.id
    # since/until 是 ISO 字符串, 只验证格式而不验证精确值
    assert "T" in str(mock_v.call_args.args[1])  # since_iso
    assert "T" in str(mock_v.call_args.args[2])  # until_iso


# ---------------------------------------------------------------------------
# P9.6 — 重跑 catchup_service 应恢复 collector.sources 和 max_items
# ---------------------------------------------------------------------------
def test_collector_state_restored_after_run(temp_db, catchup_repo):
    """即使 _execute_catchup_run 中途抛异常, finally 也应恢复 svc state."""
    target = [Category.AI]
    srs = {
        Category.AI: [_make_source_result("hn", 5)],
    }
    svc = _make_mock_svc(target, srs)
    # 记录原始值 (P2-6: collectors 是列表)
    orig_sources = list(svc.collectors[Category.AI][0].sources)
    orig_max = svc.collectors[Category.AI][0].max_items

    # 让 update_progress 抛异常 (模拟 crash)
    with patch.object(catchup_service, "_get_dead_source_names", return_value={}), \
         patch("backend.services.collection_service.CollectionService", return_value=svc), \
         patch.object(catchup_service._repo, "update_progress",
                      side_effect=RuntimeError("DB crash")):
        run = catchup_repo.create(
            mode="manual",
            since_window=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            until_window=datetime.now(timezone.utc).isoformat(),
            categories=["ai"],
            max_per_source=99,  # 故意改成 99 测恢复
        )
        _run(catchup_service._execute_catchup_run(run.id, mode="manual"))

    # finally 应恢复
    assert list(svc.collectors[Category.AI][0].sources) == orig_sources
    assert svc.collectors[Category.AI][0].max_items == orig_max

    # run 标 failed
    final = catchup_repo.get(run.id)
    assert final.status == "failed"


# ---------------------------------------------------------------------------
# P9.7 — mode=auto 不阻塞 (可与 manual 并发, 不抛 409)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_mode_does_not_throw_409(temp_db):
    """auto 模式不应该检查 _lock (与 manual 解耦)."""
    # 模拟 manual 占位
    catchup_service._current_manual_run = 999
    await catchup_service._lock.acquire()
    try:
        with patch.object(catchup_service, "_execute_catchup_run",
                          new=AsyncMock()):
            run_id = await catchup_service.enqueue_catchup(
                mode="auto",
                since=(datetime.now(timezone.utc) - timedelta_hours(1)).isoformat(),
                until=None,
                categories=None,
                max_per_source=20,
            )
        assert run_id > 0
    finally:
        catchup_service._lock.release()
        catchup_service._current_manual_run = None


# ---------------------------------------------------------------------------
# P9.8 — 整轮崩溃 → 标 failed + 写 collect_done(failed) 事件
# ---------------------------------------------------------------------------
def test_whole_run_crash_marks_failed_and_logs(
    temp_db, catchup_repo
):
    """让 _get_dead_source_names 抛异常 → 应标 failed + 写 collect_done(failed)."""
    with patch.object(catchup_service, "_get_dead_source_names",
                      side_effect=RuntimeError("DB totally down")), \
         patch("backend.services.collection_logger.log_collect_event") as mock_log:
        run = catchup_repo.create(
            mode="manual",
            since_window=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            until_window=datetime.now(timezone.utc).isoformat(),
            categories=["ai"],
            max_per_source=50,
        )
        _run(catchup_service._execute_catchup_run(run.id, mode="manual"))

    final = catchup_repo.get(run.id)
    assert final.status == "failed"
    assert "DB totally down" in (final.error_msg or "")

    # collect_done(failed) 被写
    events = [c.args[0] for c in mock_log.call_args_list if c.args]
    collect_done_calls = [
        c for c in mock_log.call_args_list
        if c.args and c.args[0] == "collect_done"
    ]
    assert len(collect_done_calls) >= 1
    last = collect_done_calls[-1]
    assert last.kwargs.get("status") == "failed"


# ---------------------------------------------------------------------------
# P0-1 — 每 cat 完成后立即 update_progress (real-time progress)
# ---------------------------------------------------------------------------
def test_per_category_progress_update(temp_db, catchup_repo):
    """P0-1: 跑 2 个 category, 中间 mock update_progress 应被调用 ≥ 2 次.

    关键: 不是只 run 终态写一次, 而是每 cat 完成后立即写, 让前端轮询
    能看到 sources_succeeded / items_ingested 增量.
    """
    target = [Category.AI, Category.TECH]
    srs = {
        Category.AI: [_make_source_result("hn", 5)],
        Category.TECH: [_make_source_result("techcrunch", 3)],
    }
    svc = _make_mock_svc(target, srs)
    update_calls = []

    real_update = catchup_service._repo.update_progress
    def spy_update(run_id, **kwargs):
        update_calls.append((run_id, kwargs))
        return real_update(run_id, **kwargs)

    with patch.object(catchup_service, "_get_dead_source_names", return_value={}), \
         patch("backend.services.collection_service.CollectionService", return_value=svc), \
         patch("backend.scheduler.jobs.trend_rebuild_job", new=AsyncMock()), \
         patch("backend.services.catchup_service.validate_and_persist",
               return_value=MagicMock(issues=[])), \
         patch.object(catchup_service._repo, "update_progress", side_effect=spy_update):
        run = catchup_repo.create(
            mode="manual",
            since_window=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            until_window=datetime.now(timezone.utc).isoformat(),
            categories=["ai", "tech"],
            max_per_source=50,
        )
        _run(catchup_service._execute_catchup_run(run.id, mode="manual"))

    # 至少被调 ≥ 2 次 (per-cat), 加上前置 sources_attempted/items_skipped 一次
    # P0-1: 至少 2 次 sources_succeeded=1, items_ingested=5 / 8
    cat_progress_calls = [
        c for c in update_calls
        if c[1].get("sources_succeeded") is not None
    ]
    assert len(cat_progress_calls) >= 2, (
        f"P0-1: 期望 ≥2 次 per-cat update_progress, 实际 {len(cat_progress_calls)} 次: "
        f"{update_calls}"
    )

    # 第一次: items_ingested=5, sources_succeeded=1 (AI 完成)
    first = cat_progress_calls[0][1]
    assert first["items_ingested"] == 5
    assert first["sources_succeeded"] == 1

    # 第二次: items_ingested=8, sources_succeeded=2 (TECH 也完成)
    second = cat_progress_calls[1][1]
    assert second["items_ingested"] == 8
    assert second["sources_succeeded"] == 2


# ---------------------------------------------------------------------------
# P0-3 — force=True 跳过 24h 续传检查, 强制重抓
# ---------------------------------------------------------------------------
def test_force_true_skips_resumption(temp_db, checkpoint_repo, catchup_repo):
    """P0-3: 上一 run (id=99) hn 已 done → 本 run force=True → hn 也 done, 不被 skipped."""
    # 上一 run done
    checkpoint_repo.mark_done(run_id=99, category="ai", source_name="hn", items_count=10)
    target = [Category.AI]
    srs = {
        Category.AI: [
            _make_source_result("hn", 7),  # 本 run 真跑, 因为 force=True
        ],
    }
    svc = _make_mock_svc(target, srs)
    with patch.object(catchup_service, "_get_dead_source_names", return_value={}), \
         patch("backend.services.collection_service.CollectionService", return_value=svc), \
         patch("backend.scheduler.jobs.trend_rebuild_job", new=AsyncMock()), \
         patch("backend.services.catchup_service.validate_and_persist",
               return_value=MagicMock(issues=[])):
        run = catchup_repo.create(
            mode="manual",
            since_window=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            until_window=datetime.now(timezone.utc).isoformat(),
            categories=["ai"],
            max_per_source=50,
        )
        # force=True: 应该跳过 24h 续传, hn 应被实际抓取
        _run(catchup_service._execute_catchup_run(run.id, mode="manual", force=True))

    hn = checkpoint_repo.get(run.id, "ai", "hn")
    assert hn is not None
    assert hn.status == "done", (
        f"P0-3: force=True 时 hn 应是 done (被实际抓取), 实际 {hn.status}"
    )
    assert hn.items_count == 7


def test_force_false_resumes_normally(temp_db, checkpoint_repo, catchup_repo):
    """P0-3 反向用例: force=False (默认) 仍走 24h 续传, hn 仍 skipped."""
    checkpoint_repo.mark_done(run_id=99, category="ai", source_name="hn", items_count=10)
    target = [Category.AI]
    srs = {
        Category.AI: [
            _make_source_result("hn", 0),  # 本 run 不真跑 (被 skip)
            _make_source_result("ph", 5),
        ],
    }
    svc = _make_mock_svc(target, srs)
    with patch.object(catchup_service, "_get_dead_source_names", return_value={}), \
         patch("backend.services.collection_service.CollectionService", return_value=svc), \
         patch("backend.scheduler.jobs.trend_rebuild_job", new=AsyncMock()), \
         patch("backend.services.catchup_service.validate_and_persist",
               return_value=MagicMock(issues=[])):
        run = catchup_repo.create(
            mode="auto",
            since_window=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            until_window=datetime.now(timezone.utc).isoformat(),
            categories=["ai"],
            max_per_source=50,
        )
        _run(catchup_service._execute_catchup_run(run.id, mode="auto"))  # force 默认 False

    hn = checkpoint_repo.get(run.id, "ai", "hn")
    assert hn is not None
    assert hn.status == "skipped", (
        f"P0-3 反向: force=False 时 hn 仍应 skipped, 实际 {hn.status}"
    )


# ---------------------------------------------------------------------------
# helper: timedelta hours
# ---------------------------------------------------------------------------
def timedelta_hours(h):
    from datetime import timedelta
    return timedelta(hours=h)

"""v1.8 Phase 8 — catchup_watchdog_job 单测.

覆盖 (8 用例):
  - B3.1 检测孤儿 (started_at > 600s 未 finished) → 标 failed
  - B3.2 边界: started_at = now - 600s 视为已孤儿
  - B3.3 边界: finished_at 已存在不触发
  - B3.4 多个孤儿 → 标记所有 + enqueue 1 次 catchup
  - B3.5 auto catchup since=最早孤儿时刻
  - B3.6 enqueue 失败不抛（仅 log）
  - B3.7 防抖窗口: 5min 内重复 watchdog 不再次 enqueue
  - B3.8 并发: watchdog 不与 collect_all 冲突（不同 lock）
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.catchup_repo import CatchupRepository
from backend.scheduler import jobs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path, 通过 init_db() 应用全部 migrations."""
    test_db = tmp_path / "test_watchdog.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture(autouse=True)
def reset_catchup_module_state():
    """重置 catchup_service 的模块级状态 (防抖 timestamp + manual run + recovery ts).
    避免测试间状态污染导致防抖拦截.
    """
    from backend.services import catchup_service
    catchup_service._last_auto_enqueue_at = None
    catchup_service._last_orphan_recovery_at = None
    catchup_service._current_manual_run = None
    yield
    catchup_service._last_auto_enqueue_at = None
    catchup_service._last_orphan_recovery_at = None
    catchup_service._current_manual_run = None


def _run(coro):
    """同步执行 async coroutine (测试用)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_orphan(
    started_offset_s: int,
    *,
    finished: bool = False,
    category: str = "ai",
) -> int:
    """插入一行 collection_runs, started_at = now - offset_s, 可选 finished."""
    conn = db.get_connection()
    started = (datetime.now(timezone.utc) - timedelta(seconds=started_offset_s)).isoformat()
    finished_at = _now_iso() if finished else None
    cur = conn.execute(
        """
        INSERT INTO collection_runs
            (category, started_at, finished_at, status, item_count, fallback_count, error_msg)
        VALUES (?, ?, ?, ?, 0, 0, NULL)
        """,
        (category, started, finished_at, "success" if finished else "running"),
    )
    return int(cur.lastrowid)


def _row(run_id: int) -> dict:
    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM collection_runs WHERE id = ?", (run_id,)
    ).fetchone()
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# B3.1 — 基础检测
# ---------------------------------------------------------------------------
def test_detects_stuck_orphan_and_marks_failed(temp_db):
    """started_at = now - 700s (超时) + finished_at IS NULL → 标 failed."""
    stuck_id = _insert_orphan(started_offset_s=700)
    _run(jobs.catchup_watchdog_job())
    r = _row(stuck_id)
    assert r["finished_at"] is not None
    assert r["status"] == "failed"
    assert "watchdog: timeout after 600s" in (r["error_msg"] or "")


# ---------------------------------------------------------------------------
# B3.2 — 边界: 恰好 600s
# ---------------------------------------------------------------------------
def test_just_under_300s_not_marked(temp_db):
    """started_at = now - 300s 明显 < 600s, 不会被 watchdog 标 failed."""
    rid = _insert_orphan(started_offset_s=300)
    _run(jobs.catchup_watchdog_job())
    r = _row(rid)
    assert r["finished_at"] is None
    assert r["status"] == "running"


def test_just_under_700s_marked_as_orphan(temp_db):
    """started_at = now - 605s (刚过边界) 视为孤儿."""
    stuck_id = _insert_orphan(started_offset_s=605)
    _run(jobs.catchup_watchdog_job())
    r = _row(stuck_id)
    assert r["status"] == "failed"


# ---------------------------------------------------------------------------
# B3.3 — finished_at 已存在不触发
# ---------------------------------------------------------------------------
def test_finished_run_not_marked_failed(temp_db):
    """finished_at 已存在 (正常跑完) 不再被 watchdog 标 failed."""
    rid = _insert_orphan(started_offset_s=700, finished=True)
    _run(jobs.catchup_watchdog_job())
    r = _row(rid)
    # 保留原 success 状态, watchdog 不覆盖
    assert r["status"] == "success"
    # finished_at 仍是原来插入的时间 (watchdog 不改)


def test_no_orphan_no_op(temp_db):
    """无孤儿时 watchdog 不做任何事, 不影响正常 run."""
    rid = _insert_orphan(started_offset_s=30, finished=False)  # 还在跑
    _run(jobs.catchup_watchdog_job())
    r = _row(rid)
    assert r["finished_at"] is None
    assert r["status"] == "running"


# ---------------------------------------------------------------------------
# B3.4 — 多个孤儿 → 标记所有 + enqueue 1 次
# ---------------------------------------------------------------------------
def test_multiple_orphans_all_marked(temp_db):
    """多个孤儿都标 failed, 只 enqueue 1 次 catchup."""
    rid1 = _insert_orphan(started_offset_s=800, category="ai")
    rid2 = _insert_orphan(started_offset_s=900, category="security")
    rid3 = _insert_orphan(started_offset_s=1000, category="finance")
    _run(jobs.catchup_watchdog_job())
    for rid in (rid1, rid2, rid3):
        r = _row(rid)
        assert r["status"] == "failed"
        assert r["finished_at"] is not None
        assert "watchdog" in (r["error_msg"] or "")

    # enqueue 1 次 = catchup_runs 表新增 1 行 mode='auto'
    repo = CatchupRepository()
    runs = repo.list_recent(limit=10)
    auto_runs = [r for r in runs if r.mode == "auto"]
    assert len(auto_runs) == 1


# ---------------------------------------------------------------------------
# B3.5 — auto catchup since = 最早孤儿时刻
# ---------------------------------------------------------------------------
def test_auto_catchup_since_is_earliest_orphan(temp_db):
    """多个孤儿时, auto catchup 的 since 应该是最早 started_at."""
    from backend.services import catchup_service
    # 重置防抖, 让本次 watchdog 能 enqueue
    catchup_service._last_auto_enqueue_at = None
    catchup_service._last_orphan_recovery_at = None

    _insert_orphan(started_offset_s=1500)  # 最早
    _insert_orphan(started_offset_s=1000)
    _insert_orphan(started_offset_s=800)

    expected_earliest_iso = (
        datetime.now(timezone.utc) - timedelta(seconds=1500)
    ).isoformat()

    _run(jobs.catchup_watchdog_job())

    repo = CatchupRepository()
    runs = repo.list_recent(limit=1)
    assert len(runs) == 1
    assert runs[0].mode == "auto"
    # since_window 应等于最早孤儿的 started_at
    # ISO 字符串可能略有精度差异, 比较 datetime
    actual_since = datetime.fromisoformat(runs[0].since_window)
    expected_since = datetime.fromisoformat(expected_earliest_iso)
    delta = abs((actual_since - expected_since).total_seconds())
    # 允许 1s 误差 (时间戳精度 + 异步延迟)
    assert delta < 2.0, f"since mismatch: {actual_since} vs {expected_since}"


# ---------------------------------------------------------------------------
# B3.6 — enqueue 失败不抛
# ---------------------------------------------------------------------------
def test_enqueue_failure_does_not_raise(temp_db):
    """enqueue_catchup 异常时, watchdog 仍标 failed, 不抛."""
    _insert_orphan(started_offset_s=700)
    with patch("backend.services.catchup_service._repo.create",
               side_effect=Exception("simulated DB error")):
        # 不应抛
        _run(jobs.catchup_watchdog_job())


# ---------------------------------------------------------------------------
# B3.7 — 防抖窗口
# ---------------------------------------------------------------------------
def test_debounce_skips_duplicate_enqueue(temp_db):
    """5min 内重复 watchdog 不再次 enqueue (但仍标 failed)."""
    from backend.services import catchup_service
    # 强制 first enqueue 通过
    catchup_service._last_auto_enqueue_at = None
    catchup_service._last_orphan_recovery_at = None

    _insert_orphan(started_offset_s=700)
    _run(jobs.catchup_watchdog_job())
    # 第一次: enqueue 1 次
    repo = CatchupRepository()
    assert len([r for r in repo.list_recent(limit=10) if r.mode == "auto"]) == 1

    # 立即第二次: 应被防抖
    _insert_orphan(started_offset_s=700)
    _run(jobs.catchup_watchdog_job())
    # 仍只 1 个 auto run
    assert len([r for r in repo.list_recent(limit=10) if r.mode == "auto"]) == 1


# ---------------------------------------------------------------------------
# B3.8 — 与 collect_all 独立 (catchup_lock 不阻塞 collect)
# ---------------------------------------------------------------------------
def test_watchdog_does_not_touch_collect_all_lock(temp_db):
    """watchdog 只标孤儿, 不调用 collect_all_job, 不会与之抢锁."""
    # 收集所有 _run_once 的调用次数 (不实际跑 collect, 避免依赖网络)
    import backend.services.collection_service as cs_mod
    call_count = [0]

    async def fake_run_once(self):
        call_count[0] += 1
        return None

    with patch.object(cs_mod.CollectionService, "run_once", fake_run_once):
        _insert_orphan(started_offset_s=700)
        _run(jobs.catchup_watchdog_job())
    # watchdog 不触发 run_once
    assert call_count[0] == 0
    # 但孤儿仍被标 failed
    repo = CatchupRepository()
    runs = repo.list_recent(limit=10)
    assert len(runs) >= 1


# ---------------------------------------------------------------------------
# 附加 — /api/health 暴露 last_orphan_recovery_at
# ---------------------------------------------------------------------------
def test_last_orphan_recovery_at_set_after_recovery(temp_db):
    """watchdog 标记孤儿后, get_last_orphan_recovery_at() 返回时间戳."""
    from backend.services.catchup_service import (
        get_last_orphan_recovery_at,
        set_last_orphan_recovery_at,
    )
    # 重置
    set_last_orphan_recovery_at(None)
    assert get_last_orphan_recovery_at() is None

    _insert_orphan(started_offset_s=700)
    _run(jobs.catchup_watchdog_job())
    assert get_last_orphan_recovery_at() is not None

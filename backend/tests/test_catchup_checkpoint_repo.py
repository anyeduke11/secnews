"""v1.9 Phase 9 — catchup_checkpoint_repo (per-source 断点续传) 单测.

覆盖 (10 用例):
  - R1.1 插入新 checkpoint → 返 rowid
  - R1.2 重复 upsert 同 (run, cat, src) → 不抛, 走 UPDATE
  - R1.3 mark_done / mark_failed / mark_skipped 便利方法
  - R1.4 list_for_run 返回该 run 全部 checkpoint
  - R1.5 count_for_run 按 status 过滤
  - R1.6 list_recent_done: 跨 run 找最近的 done
  - R1.7 list_recent_done with since_iso: 限定窗口
  - R1.8 upsert 非法 status → raise ValueError
  - R1.9 get(run, cat, src) → 返 Checkpoint
  - R1.10 续传语义: 上一 run 已 done → 本 run 可查出来 (skip 决策依据)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.catchup_checkpoint_repo import (
    CatchupCheckpointRepository,
    CheckpointStatus,
)
from backend.repository.db import get_connection


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_catchup_checkpoint.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def repo(temp_db) -> CatchupCheckpointRepository:
    return CatchupCheckpointRepository()


# ---------------------------------------------------------------------------
# R1.1 — 插入新 checkpoint
# ---------------------------------------------------------------------------
def test_upsert_inserts_new_pending(repo: CatchupCheckpointRepository):
    cid = repo.upsert(
        run_id=1, category="ai", source_name="hacker_news",
        status="pending",
    )
    assert cid > 0
    ck = repo.get(1, "ai", "hacker_news")
    assert ck is not None
    assert ck.status == "pending"
    assert ck.items_count == 0
    assert ck.started_at is not None
    assert ck.finished_at is None


# ---------------------------------------------------------------------------
# R1.2 — 重复 upsert → UPDATE 不抛
# ---------------------------------------------------------------------------
def test_upsert_updates_existing(repo: CatchupCheckpointRepository):
    cid1 = repo.upsert(
        run_id=1, category="ai", source_name="hn",
        status="pending",
    )
    # 第二次: 标 done + items=15
    cid2 = repo.upsert(
        run_id=1, category="ai", source_name="hn",
        status="done", items_count=15,
    )
    # 两次应该都返回同一 row id
    assert cid1 == cid2
    ck = repo.get(1, "ai", "hn")
    assert ck.status == "done"
    assert ck.items_count == 15
    assert ck.finished_at is not None  # done → 写 finished_at


# ---------------------------------------------------------------------------
# R1.3 — 便利方法
# ---------------------------------------------------------------------------
def test_mark_done_failed_skipped_convenience(repo: CatchupCheckpointRepository):
    repo.mark_done(run_id=1, category="ai", source_name="hn", items_count=10)
    repo.mark_failed(run_id=1, category="ai", source_name="broken", error_msg="timeout")
    repo.mark_skipped(
        run_id=1, category="ai", source_name="skipme",
        reason="resumed from prior run",
    )

    done = repo.get(1, "ai", "hn")
    assert done.status == "done"
    assert done.items_count == 10

    failed = repo.get(1, "ai", "broken")
    assert failed.status == "failed"
    assert failed.error_msg == "timeout"

    skipped = repo.get(1, "ai", "skipme")
    assert skipped.status == "skipped"
    assert "resumed" in (skipped.error_msg or "")


# ---------------------------------------------------------------------------
# R1.4 — list_for_run
# ---------------------------------------------------------------------------
def test_list_for_run_returns_all_checkpoints_for_run(
    repo: CatchupCheckpointRepository,
):
    repo.mark_done(run_id=10, category="ai", source_name="a1", items_count=5)
    repo.mark_done(run_id=10, category="ai", source_name="a2", items_count=7)
    repo.mark_done(run_id=11, category="ai", source_name="a1", items_count=3)  # 其他 run

    rows = repo.list_for_run(10)
    assert len(rows) == 2
    names = {r.source_name for r in rows}
    assert names == {"a1", "a2"}


# ---------------------------------------------------------------------------
# R1.5 — count_for_run 按 status 过滤
# ---------------------------------------------------------------------------
def test_count_for_run_by_status(repo: CatchupCheckpointRepository):
    repo.mark_done(run_id=20, category="ai", source_name="a", items_count=5)
    repo.mark_failed(run_id=20, category="ai", source_name="b", error_msg="x")
    repo.mark_skipped(run_id=20, category="ai", source_name="c")

    assert repo.count_for_run(20) == 3
    assert repo.count_for_run(20, status="done") == 1
    assert repo.count_for_run(20, status="failed") == 1
    assert repo.count_for_run(20, status="skipped") == 1
    assert repo.count_for_run(20, status="pending") == 0


# ---------------------------------------------------------------------------
# R1.6 — list_recent_done: 跨 run 找最近 done
# ---------------------------------------------------------------------------
def test_list_recent_done_cross_run(repo: CatchupCheckpointRepository):
    repo.mark_done(run_id=30, category="ai", source_name="hn", items_count=5)
    # 同 source 第二个 run 也 done
    repo.mark_done(run_id=31, category="ai", source_name="hn", items_count=7)

    recent = repo.list_recent_done("ai", "hn", limit=1)
    assert len(recent) == 1
    # 应该是最新 (run 31)
    assert recent[0].run_id == 31
    assert recent[0].items_count == 7


# ---------------------------------------------------------------------------
# R1.7 — list_recent_done with since_iso: 限定窗口
# ---------------------------------------------------------------------------
def test_list_recent_done_with_since_filter(repo: CatchupCheckpointRepository):
    # 手工写一行: finished_at 设为 7 天前
    conn = get_connection()
    seven_days_ago = (
        datetime.now(timezone.utc) - timedelta(days=7)
    ).isoformat()
    conn.execute(
        """
        INSERT INTO catchup_checkpoints
            (run_id, category, source_name, status, items_count,
             started_at, finished_at)
        VALUES (?, 'ai', 'old', 'done', 5, ?, ?)
        """,
        (40, seven_days_ago, seven_days_ago),
    )
    # 新的 done
    repo.mark_done(run_id=41, category="ai", source_name="old", items_count=3)

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent = repo.list_recent_done("ai", "old", since_iso=cutoff, limit=10)
    # 只返 run 41 (新), 不返 40 (7 天前)
    assert len(recent) == 1
    assert recent[0].run_id == 41


# ---------------------------------------------------------------------------
# R1.8 — 非法 status
# ---------------------------------------------------------------------------
def test_upsert_invalid_status_raises(repo: CatchupCheckpointRepository):
    with pytest.raises(ValueError, match="invalid checkpoint status"):
        repo.upsert(
            run_id=1, category="ai", source_name="hn",
            status="bogus",
        )


# ---------------------------------------------------------------------------
# R1.9 — get
# ---------------------------------------------------------------------------
def test_get_returns_none_when_missing(repo: CatchupCheckpointRepository):
    assert repo.get(999, "ai", "ghost") is None


# ---------------------------------------------------------------------------
# R1.10 — 续传语义: 上次 done → 这次预判可跳过
# ---------------------------------------------------------------------------
def test_resumption_decision_logic(repo: CatchupCheckpointRepository):
    """核心业务场景: 上一 run (id=50) 已 done, 本 run (id=51) 该 source 复用.

    catchup_service 集成时: list_recent_done(...) 非空 → mark_skipped(本 run).
    """
    repo.mark_done(run_id=50, category="ai", source_name="hn", items_count=5)
    # 模拟本 run 启动 → 查 list_recent_done
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent = repo.list_recent_done("ai", "hn", since_iso=cutoff, limit=1)
    assert recent  # 上一 run 已 done
    # → catchup_service 决策: 跳过本 run
    repo.mark_skipped(run_id=51, category="ai", source_name="hn",
                      reason="resumed from prior run")
    # 验证
    skipped = repo.get(51, "ai", "hn")
    assert skipped.status == "skipped"
    assert "resumed" in (skipped.error_msg or "")

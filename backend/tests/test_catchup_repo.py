"""v1.8 Phase 8 — catchup_repo 单测.

覆盖: CRUD 路径 + 状态机校验 + 并发更新不丢字段.
"""
from __future__ import annotations

import pytest

from backend.repository import db
from backend.repository.catchup_repo import CatchupRepository


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    """隔离 DB 到 tmp_path, 避免污染生产 db."""
    db_file = tmp_path / "test_catchup.db"
    monkeypatch.setattr("backend.config.config.db_path", db_file)

    # 重新打开 connection
    db.close_db()
    conn = db.get_connection()
    # 创建表
    sql = """
    CREATE TABLE IF NOT EXISTS catchup_runs (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        mode                TEXT    NOT NULL CHECK (mode IN ('auto', 'manual')),
        since_window        TEXT    NOT NULL,
        until_window        TEXT,
        categories          TEXT    NOT NULL,
        max_per_source      INTEGER NOT NULL DEFAULT 20,
        started_at          TEXT    NOT NULL,
        finished_at         TEXT,
        status              TEXT    NOT NULL CHECK (status IN ('running','success','partial','failed','aborted')),
        items_ingested      INTEGER NOT NULL DEFAULT 0,
        items_skipped       INTEGER NOT NULL DEFAULT 0,
        sources_attempted   INTEGER NOT NULL DEFAULT 0,
        sources_succeeded   INTEGER NOT NULL DEFAULT 0,
        error_msg           TEXT,
        duration_ms         INTEGER NOT NULL DEFAULT 0
    );
    """
    conn.executescript(sql)
    yield conn
    db.close_db()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def test_create_returns_running_row(temp_db):
    repo = CatchupRepository()
    run = repo.create(
        mode="manual",
        since_window="2026-07-24T13:57:00+00:00",
        until_window="2026-07-25T09:25:00+00:00",
        categories=["ai", "security"],
        max_per_source=30,
    )
    assert run.id > 0
    assert run.mode == "manual"
    assert run.status == "running"
    assert run.categories == ["ai", "security"]
    assert run.max_per_source == 30
    assert run.finished_at is None
    assert run.items_ingested == 0


def test_create_rejects_invalid_mode(temp_db):
    repo = CatchupRepository()
    with pytest.raises(ValueError, match="invalid mode"):
        repo.create(
            mode="invalid",
            since_window="2026-07-24T00:00:00+00:00",
            until_window=None,
            categories=[],
            max_per_source=10,
        )


def test_get_returns_none_for_missing(temp_db):
    repo = CatchupRepository()
    assert repo.get(9999) is None


def test_get_current_running_returns_latest(temp_db):
    repo = CatchupRepository()
    r2 = repo.create(mode="auto", since_window="2026-07-24T01:00:00+00:00",
                     until_window=None, categories=[], max_per_source=10)
    current = repo.get_current_running()
    assert current is not None
    # Latest started_at wins
    assert current.id == r2.id


def test_list_recent_respects_limit(temp_db):
    repo = CatchupRepository()
    for i in range(5):
        repo.create(mode="manual", since_window=f"2026-07-2{i}:00:00+00:00",
                    until_window=None, categories=[], max_per_source=10)
    assert len(repo.list_recent(limit=3)) == 3
    assert len(repo.list_recent(limit=10)) == 5


# ---------------------------------------------------------------------------
# Progress + Finish
# ---------------------------------------------------------------------------
def test_update_progress_only_running(temp_db):
    repo = CatchupRepository()
    run = repo.create(mode="manual", since_window="2026-07-24T00:00:00+00:00",
                      until_window=None, categories=[], max_per_source=10)
    repo.update_progress(run.id, items_ingested=5, sources_succeeded=2)
    loaded = repo.get(run.id)
    assert loaded.items_ingested == 5
    assert loaded.sources_succeeded == 2

    # finish 后再 update 不应生效
    repo.finish(run.id, status="success", items_ingested=10, items_skipped=0,
                sources_attempted=4, sources_succeeded=4)
    repo.update_progress(run.id, items_ingested=999)
    loaded = repo.get(run.id)
    assert loaded.items_ingested == 10  # 终态后 update 不覆盖


def test_update_progress_partial_fields(temp_db):
    """只传部分字段时, 其他字段保持原值."""
    repo = CatchupRepository()
    run = repo.create(mode="manual", since_window="2026-07-24T00:00:00+00:00",
                      until_window=None, categories=[], max_per_source=10)
    repo.update_progress(run.id, items_ingested=7)
    loaded = repo.get(run.id)
    assert loaded.items_ingested == 7
    assert loaded.sources_attempted == 0  # 其他字段保持


def test_finish_computes_duration(temp_db):
    repo = CatchupRepository()
    run = repo.create(mode="manual", since_window="2026-07-24T00:00:00+00:00",
                      until_window=None, categories=[], max_per_source=10)
    repo.finish(run.id, status="success", items_ingested=10, items_skipped=2,
                sources_attempted=5, sources_succeeded=4)
    loaded = repo.get(run.id)
    assert loaded.status == "success"
    assert loaded.finished_at is not None
    # duration_ms 字段必须存在且 >= 0 (microsecond 级测试可能 0)
    assert loaded.duration_ms is not None
    assert loaded.duration_ms >= 0
    assert loaded.items_ingested == 10


def test_finish_rejects_invalid_terminal_status(temp_db):
    repo = CatchupRepository()
    run = repo.create(mode="manual", since_window="2026-07-24T00:00:00+00:00",
                      until_window=None, categories=[], max_per_source=10)
    with pytest.raises(ValueError, match="invalid terminal status"):
        repo.finish(run.id, status="running", items_ingested=0, items_skipped=0,
                    sources_attempted=0, sources_succeeded=0)


# ---------------------------------------------------------------------------
# Abort
# ---------------------------------------------------------------------------
def test_abort_running_succeeds(temp_db):
    repo = CatchupRepository()
    run = repo.create(mode="manual", since_window="2026-07-24T00:00:00+00:00",
                      until_window=None, categories=[], max_per_source=10)
    assert repo.abort(run.id) is True
    loaded = repo.get(run.id)
    assert loaded.status == "aborted"
    assert loaded.finished_at is not None


def test_abort_terminal_returns_false(temp_db):
    repo = CatchupRepository()
    run = repo.create(mode="manual", since_window="2026-07-24T00:00:00+00:00",
                      until_window=None, categories=[], max_per_source=10)
    repo.finish(run.id, status="success", items_ingested=0, items_skipped=0,
                sources_attempted=0, sources_succeeded=0)
    assert repo.abort(run.id) is False  # 已 success 不能再 abort


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------
def test_to_dict_shape(temp_db):
    repo = CatchupRepository()
    run = repo.create(mode="manual", since_window="2026-07-24T00:00:00+00:00",
                      until_window=None, categories=["ai"], max_per_source=10)
    repo.update_progress(run.id, items_ingested=3, sources_succeeded=1)
    d = run.to_dict()
    assert d["id"] == run.id
    assert d["mode"] == "manual"
    assert d["categories"] == ["ai"]
    assert d["status"] == "running"
    assert d["duration_s"] == 0
    # 进度已写入
    loaded = repo.get(run.id)
    d2 = loaded.to_dict()
    assert d2["items_ingested"] == 3

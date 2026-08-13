"""SourceSchedulerRepository 单元测试

每个测试使用 tmp_path 隔离的临时 SQLite，通过 monkeypatch
替换 ``get_connection`` 避免污染真实数据库。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest

from backend.repository.source_scheduler_repo import SourceSchedulerRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def repo(tmp_path, monkeypatch) -> Iterator[SourceSchedulerRepository]:
    """独立临时 DB, 加载 migration 055 的 crawler_sources + crawler_runs."""
    db_file = tmp_path / "test_scheduler.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA journal_mode=WAL")
    # 从 migration 055 提取 crawler_sources + crawler_runs DDL
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS crawler_sources (
            id                  TEXT PRIMARY KEY,
            category            TEXT NOT NULL,
            name                TEXT NOT NULL,
            kind                TEXT NOT NULL DEFAULT 'html',
            parser_id           TEXT NOT NULL DEFAULT '',
            url                 TEXT,
            feed_url            TEXT,
            api_url             TEXT,
            cadence_seconds     INTEGER NOT NULL DEFAULT 300,
            priority            INTEGER NOT NULL DEFAULT 50,
            max_items           INTEGER NOT NULL DEFAULT 50,
            enabled             INTEGER NOT NULL DEFAULT 1,
            use_proxy           TEXT NOT NULL DEFAULT 'auto',
            headers             TEXT,
            verify_ssl          INTEGER NOT NULL DEFAULT 1,
            etag                TEXT,
            last_modified       TEXT,
            last_fetch_at       TEXT,
            last_success_at     TEXT,
            last_yield_at       TEXT,
            last_error          TEXT,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            cooldown_until      TEXT,
            health_score        REAL NOT NULL DEFAULT 1.0,
            status              TEXT NOT NULL DEFAULT 'active',
            first_fetch         INTEGER NOT NULL DEFAULT 1,
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS crawler_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id       TEXT NOT NULL,
            category        TEXT NOT NULL,
            started_at      TEXT NOT NULL,
            finished_at     TEXT,
            status          TEXT NOT NULL DEFAULT 'running',
            fetched_count   INTEGER NOT NULL DEFAULT 0,
            accepted_count  INTEGER NOT NULL DEFAULT 0,
            error_msg       TEXT DEFAULT '',
            duration_ms     INTEGER NOT NULL DEFAULT 0,
            parser_version  TEXT DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()

    from backend.repository import db as db_mod
    from backend.repository import source_scheduler_repo as repo_mod

    def _get_conn():
        c = sqlite3.connect(str(db_file), isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    monkeypatch.setattr(db_mod, "get_connection", _get_conn)
    monkeypatch.setattr(repo_mod, "get_connection", _get_conn)

    yield SourceSchedulerRepository()


# ---------------------------------------------------------------------------
# Helpers — 使用 repo 背后的 get_connection 写入数据
# ---------------------------------------------------------------------------
def _conn():
    from backend.repository import db as db_mod
    return db_mod.get_connection()


def _insert_source(
    id: str,
    *,
    name: str = "test-source",
    category: str = "security",
    priority: int = 50,
    enabled: int = 1,
    status: str = "active",
    cooldown_until: str | None = None,
    consecutive_failures: int = 0,
    health_score: float = 1.0,
    **kw,
) -> None:
    fields = {
        "id": id,
        "name": name,
        "category": category,
        "priority": priority,
        "enabled": enabled,
        "status": status,
        "cooldown_until": cooldown_until,
        "consecutive_failures": consecutive_failures,
        "health_score": health_score,
        **kw,
    }
    placeholders = ", ".join(f":{k}" for k in fields)
    cols = ", ".join(fields)
    _conn().execute(
        f"INSERT INTO crawler_sources ({cols}) VALUES ({placeholders})",
        fields,
    )


def _insert_run(
    source_id: str,
    *,
    category: str = "security",
    status: str = "success",
    fetched_count: int = 10,
    accepted_count: int = 8,
    duration_ms: int = 500,
    started_at: str | None = None,
) -> None:
    if started_at is None:
        # SQLite 兼容格式（空格分隔）以便与 datetime('now') 做字符串比较
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    _conn().execute(
        """INSERT INTO crawler_runs
           (source_id, category, status, fetched_count, accepted_count,
            duration_ms, started_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source_id, category, status, fetched_count, accepted_count,
         duration_ms, started_at),
    )


# ---------------------------------------------------------------------------
# get_schedulable
# ---------------------------------------------------------------------------
class TestGetSchedulable:
    def test_returns_only_enabled_non_dead_sources(self, repo):
        """只返回 enabled=1 且 status 非 dead/disabled 的源。"""
        _insert_source("s1", name="good", priority=50, enabled=1, status="active")
        _insert_source("s2", name="dead-one", priority=50, enabled=1, status="dead")
        _insert_source("s3", name="disabled-one", priority=50, enabled=1, status="disabled")
        _insert_source("s4", name="disabled-flag", priority=50, enabled=0, status="active")

        result = repo.get_schedulable(limit=10)
        ids = [r["id"] for r in result]
        assert "s1" in ids
        assert "s2" not in ids
        assert "s3" not in ids
        assert "s4" not in ids

    def test_sorted_by_priority_desc(self, repo):
        """按 priority DESC 排序。"""
        _insert_source("low", name="low", priority=10, enabled=1, status="active")
        _insert_source("high", name="high", priority=90, enabled=1, status="active")
        _insert_source("mid", name="mid", priority=50, enabled=1, status="active")

        result = repo.get_schedulable(limit=10)
        priorities = [r["priority"] for r in result]
        assert priorities == sorted(priorities, reverse=True)

    def test_respects_limit(self, repo):
        """limit 参数限制返回条数。"""
        for i in range(5):
            _insert_source(f"s{i}", name=f"src-{i}", priority=50, enabled=1, status="active")

        result = repo.get_schedulable(limit=3)
        assert len(result) == 3

    def test_excludes_sources_in_cooldown(self, repo):
        """cooldown_until 大于当前时间的源应被排除。"""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        _insert_source("cooling", name="cooldown", priority=50, enabled=1, status="active", cooldown_until=future)
        _insert_source("ready", name="ready", priority=50, enabled=1, status="active", cooldown_until=past)
        _insert_source("no-cooldown", name="no-cd", priority=50, enabled=1, status="active", cooldown_until=None)

        result = repo.get_schedulable(limit=10, now_iso=datetime.now(timezone.utc).isoformat())
        ids = [r["id"] for r in result]
        assert "cooling" not in ids
        assert "ready" in ids
        assert "no-cooldown" in ids

    def test_uses_sqlite_now_when_now_iso_none(self, repo):
        """now_iso=None 时使用 SQLite datetime('now')。"""
        # 使用 SQLite 兼容格式（空格分隔，无毫秒）以便与 datetime('now') 做字符串比较
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_source("ok", name="ok", priority=50, enabled=1, status="active", cooldown_until=past)
        _insert_source("active-src", name="active", priority=50, enabled=1, status="active", cooldown_until=None)

        result = repo.get_schedulable(limit=10)
        ids = [r["id"] for r in result]
        assert "ok" in ids
        assert "active-src" in ids


# ---------------------------------------------------------------------------
# update_health_state
# ---------------------------------------------------------------------------
class TestUpdateHealthState:
    def test_updates_specified_fields(self, repo):
        _insert_source("s1", name="test", status="active", consecutive_failures=0)

        ok = repo.update_health_state("s1", status="dead", consecutive_failures=3)
        assert ok is True

        row = _conn().execute(
            "SELECT status, consecutive_failures FROM crawler_sources WHERE id = ?",
            ("s1",),
        ).fetchone()
        assert row["status"] == "dead"
        assert row["consecutive_failures"] == 3

    def test_also_sets_updated_at(self, repo):
        _insert_source("s1", name="test", status="active")

        repo.update_health_state("s1", status="grace")
        row = _conn().execute(
            "SELECT updated_at FROM crawler_sources WHERE id = ?",
            ("s1",),
        ).fetchone()
        assert row["updated_at"] is not None

    def test_returns_true_for_existing_source(self, repo):
        _insert_source("s1", name="test")

        ok = repo.update_health_state("s1", health_score=0.5)
        assert ok is True

    def test_returns_false_for_nonexistent_source(self, repo):
        ok = repo.update_health_state("nonexistent", status="dead")
        assert ok is False

    def test_returns_false_when_no_fields(self, repo):
        ok = repo.update_health_state("s1")
        assert ok is False


# ---------------------------------------------------------------------------
# get_run_stats
# ---------------------------------------------------------------------------
class TestGetRunStats:
    def test_returns_correct_stats(self, repo):
        _insert_source("s1", name="test")

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        _insert_run("s1", status="success", fetched_count=20, accepted_count=15,
                     duration_ms=400, started_at=now)
        _insert_run("s1", status="failed", fetched_count=10, accepted_count=0,
                     duration_ms=600, started_at=now)

        stats = repo.get_run_stats("s1", since_hours=24)
        assert stats["total_runs"] == 2
        assert stats["failed_runs"] == 1
        assert stats["total_fetched"] == 30
        assert stats["total_accepted"] == 15
        assert stats["avg_duration_ms"] == 500.0
        # rejection_rate = (30-15)/30 = 0.5
        assert stats["rejection_rate"] == 0.5

    def test_handles_empty_stats(self, repo):
        """至少返回零值而不抛异常。"""
        stats = repo.get_run_stats("nonexistent", since_hours=24)
        assert stats["total_runs"] == 0
        assert stats["failed_runs"] == 0
        assert stats["total_fetched"] == 0
        assert stats["total_accepted"] == 0
        assert stats["avg_duration_ms"] == 0.0
        assert stats["rejection_rate"] == 0.0

    def test_respects_since_hours(self, repo):
        _insert_source("s1", name="test")

        # 使用 SQLite 兼容格式（空格分隔）以便与 datetime('now', ?) 做字符串比较
        # 25 小时前的运行 — 超出窗口
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_run("s1", status="success", started_at=old)
        # 1 小时前的运行 — 在窗口内
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        _insert_run("s1", status="success", started_at=recent)

        stats = repo.get_run_stats("s1", since_hours=24)
        assert stats["total_runs"] == 1


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------
class TestGetById:
    def test_returns_dict_for_existing_source(self, repo):
        _insert_source("s1", name="my-source", category="ai", priority=80)

        source = repo.get_by_id("s1")
        assert source is not None
        assert source["id"] == "s1"
        assert source["name"] == "my-source"
        assert source["category"] == "ai"
        assert source["priority"] == 80

    def test_returns_none_for_missing_source(self, repo):
        source = repo.get_by_id("nonexistent")
        assert source is None


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------
class TestListAll:
    def test_returns_all_sources_sorted_by_category_priority_desc(self, repo):
        _insert_source("s1", name="a", category="ai", priority=50)
        _insert_source("s2", name="b", category="security", priority=90)
        _insert_source("s3", name="c", category="security", priority=10)
        _insert_source("s4", name="d", category="ai", priority=80)

        result = repo.list_all()
        assert len(result) == 4

        # 期望顺序: ai(80), ai(50), security(90), security(10)
        expected = [
            ("s4", "ai", 80),
            ("s1", "ai", 50),
            ("s2", "security", 90),
            ("s3", "security", 10),
        ]
        for i, (exp_id, exp_cat, exp_pri) in enumerate(expected):
            assert result[i]["id"] == exp_id, (
                f"position {i}: expected {exp_id}, got {result[i]['id']}"
            )
            assert result[i]["category"] == exp_cat
            assert result[i]["priority"] == exp_pri

    def test_includes_disabled_and_dead_sources(self, repo):
        """list_all 返回所有源，不筛选。"""
        _insert_source("s1", name="active", status="active")
        _insert_source("s2", name="dead", status="dead")
        _insert_source("s3", name="disabled", status="disabled")

        result = repo.list_all()
        assert len(result) == 3


# ---------------------------------------------------------------------------
# get_stats_summary
# ---------------------------------------------------------------------------
class TestGetStatsSummary:
    def test_counts_by_status(self, repo):
        _insert_source("s1", status="active")
        _insert_source("s2", status="active")
        _insert_source("s3", status="grace")
        _insert_source("s4", status="stale")
        _insert_source("s5", status="dead")
        _insert_source("s6", status="disabled")

        summary = repo.get_stats_summary()
        assert summary["total"] == 6
        assert summary["active"] == 2
        assert summary["grace"] == 1
        assert summary["stale"] == 1
        assert summary["dead"] == 1
        assert summary["disabled"] == 1

    def test_calculates_active_rate(self, repo):
        _insert_source("s1", status="active")
        _insert_source("s2", status="active")
        _insert_source("s3", status="active")
        _insert_source("s4", status="dead")

        summary = repo.get_stats_summary()
        assert summary["active_rate"] == 0.75

    def test_handles_empty_table(self, repo):
        summary = repo.get_stats_summary()
        assert summary["total"] == 0
        assert summary["active"] == 0
        assert summary["grace"] == 0
        assert summary["stale"] == 0
        assert summary["dead"] == 0
        assert summary["disabled"] == 0
        assert summary["active_rate"] == 0.0
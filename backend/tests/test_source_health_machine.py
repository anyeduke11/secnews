"""Tests for SourceHealthMachine — 5-state health state machine.

Covers:
- All 7 state transition paths
- Backoff cooldown calculation
- Health score calculation
- Unknown source handling
- Disabled source skip
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services.source_health_machine import (
    BACKOFF_BASE,
    BACKOFF_MAX_EXPONENT,
    DEAD_THRESHOLD,
    GRACE_FAIL_THRESHOLD,
    STALE_THRESHOLD,
    SourceHealthMachine,
    _calculate_cooldown,
)

# ---------------------------------------------------------------------------
# 夹具: 临时 SQLite 数据库 + monkeypatch get_connection
# ---------------------------------------------------------------------------

_CRAWLER_SOURCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS crawler_sources (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    health_score        REAL NOT NULL DEFAULT 1.0,
    cooldown_until      TEXT,
    grace_rounds        INTEGER NOT NULL DEFAULT 0,
    last_success_at     TEXT,
    last_yield_at       TEXT,
    last_error          TEXT,
    last_fetch_at       TEXT,
    enabled             INTEGER NOT NULL DEFAULT 1,
    priority            INTEGER NOT NULL DEFAULT 50,
    category            TEXT,
    created_at          TEXT,
    updated_at          TEXT
);
"""


@pytest.fixture
def db_conn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sqlite3.Connection:
    """创建临时 SQLite DB, 替换 get_connection, 返回连接."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(_CRAWLER_SOURCES_SCHEMA)

    from backend.services import source_health_machine as shm_mod

    monkeypatch.setattr(shm_mod, "get_connection", lambda: conn)
    return conn


@pytest.fixture
def machine() -> SourceHealthMachine:
    return SourceHealthMachine()


def _insert_source(
    conn: sqlite3.Connection,
    source_id: str = "test-src",
    status: str = "active",
    consecutive_failures: int = 0,
    health_score: float = 1.0,
    grace_rounds: int = 0,
    cooldown_until: str | None = None,
    enabled: int = 1,
    name: str = "Test Source",
    priority: int = 50,
) -> None:
    conn.execute(
        """INSERT INTO crawler_sources
           (id, name, status, consecutive_failures, health_score,
            grace_rounds, cooldown_until, enabled, priority, category,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                   datetime('now'), datetime('now'))""",
        (source_id, name, status, consecutive_failures, health_score,
         grace_rounds, cooldown_until, enabled, priority, 'test'),
    )


def _run_result(
    fetched_count: int = 0,
    status: str = "failed",
    error_msg: str = "",
) -> dict:
    return {
        "fetched_count": fetched_count,
        "accepted_count": fetched_count,
        "status": status,
        "duration_ms": 100,
        "error_msg": error_msg,
    }


# ===================================================================
# 健康评分
# ===================================================================


class TestHealthScore:
    def test_zero_failures(self):
        assert SourceHealthMachine._calculate_health_score(0) == 1.0

    def test_one_failure(self):
        assert SourceHealthMachine._calculate_health_score(1) == 0.9

    def test_two_failures(self):
        assert SourceHealthMachine._calculate_health_score(2) == 0.7

    def test_three_failures(self):
        assert SourceHealthMachine._calculate_health_score(3) == 0.5

    def test_four_failures(self):
        assert SourceHealthMachine._calculate_health_score(4) == 0.3

    def test_five_or_more_failures(self):
        assert SourceHealthMachine._calculate_health_score(5) == 0.1
        assert SourceHealthMachine._calculate_health_score(10) == 0.1
        assert SourceHealthMachine._calculate_health_score(99) == 0.1


# ===================================================================
# 指数退避冷却
# ===================================================================


class TestCooldown:
    def test_cooldown_returns_future_iso_string(self):
        """返回的 cooldown 是未来的 ISO 时间字符串."""
        result = _calculate_cooldown(5)
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo is not None
        assert dt > datetime.now(timezone.utc)

    def test_cooldown_delay_monotonic(self):
        """失败次数越高, cooldown 越晚."""
        t5 = datetime.fromisoformat(_calculate_cooldown(5))
        t6 = datetime.fromisoformat(_calculate_cooldown(6))
        t7 = datetime.fromisoformat(_calculate_cooldown(7))
        assert t5 < t6 < t7

    def test_cooldown_capped_at_max_exponent(self):
        """超过 BACKOFF_MAX_EXPONENT 后不再增长."""
        cap = datetime.fromisoformat(_calculate_cooldown(11 + BACKOFF_MAX_EXPONENT))
        beyond = datetime.fromisoformat(_calculate_cooldown(99))
        # 两次调用时间差应在毫秒级（只差 _now_utc() 的调用时刻）
        delta = abs((beyond - cap).total_seconds())
        assert delta < 1.0  # 小于 1 秒, 说明指数已封顶

    def test_cooldown_low_failures(self):
        """失败次数 <= 5 时, 指数为 0, 延迟 = 1 * BACKOFF_BASE."""
        low = datetime.fromisoformat(_calculate_cooldown(3))
        now = datetime.now(timezone.utc)
        # 3 < 5, 所以 exponent = max(0, min(3-5, 6)) = max(0, min(-2, 6)) = 0
        # delay = 1 * 300 = 300s
        expected_lower = now + timedelta(seconds=BACKOFF_BASE - 10)
        expected_upper = now + timedelta(seconds=BACKOFF_BASE + 10)
        assert expected_lower <= low <= expected_upper

    def test_cooldown_precise_exponent(self):
        """验证指数退避的精确延迟."""
        # failures=5 → exponent=0 → delay=300s
        # failures=6 → exponent=1 → delay=600s
        # failures=7 → exponent=2 → delay=1200s
        # failures=8 → exponent=3 → delay=2400s
        t5 = datetime.fromisoformat(_calculate_cooldown(5))
        t6 = datetime.fromisoformat(_calculate_cooldown(6))
        t7 = datetime.fromisoformat(_calculate_cooldown(7))
        t8 = datetime.fromisoformat(_calculate_cooldown(8))
        # 每步增长约 2^(n-1) * 300 秒
        delta_5_6 = (t6 - t5).total_seconds()
        delta_6_7 = (t7 - t6).total_seconds()
        delta_7_8 = (t8 - t7).total_seconds()
        # 5→6: 额外 300s, 6→7: 额外 600s, 7→8: 额外 1200s
        assert 250 <= delta_5_6 <= 350
        assert 550 <= delta_6_7 <= 650
        assert 1150 <= delta_7_8 <= 1250


# ===================================================================
# 状态转换
# ===================================================================


class TestTransitions:
    """Test ALL 7 state transition paths."""

    # -------------------------------
    # 1. active → stale (3 consecutive failures)
    # -------------------------------

    def test_active_to_stale(self, db_conn, machine: SourceHealthMachine):
        _insert_source(db_conn, "src1", status="active", consecutive_failures=0)

        # 第 1 次失败: 仍 active, consec=1
        r1 = machine.apply_run_result("src1", _run_result(fetched_count=0, status="failed"))
        assert r1["previous_status"] == "active"
        assert r1["new_status"] == "active"
        assert r1["consecutive_failures"] == 1
        assert r1["transition"] == "failure_incremented"

        # 第 2 次失败: 仍 active, consec=2
        r2 = machine.apply_run_result("src1", _run_result(fetched_count=0, status="failed"))
        assert r2["new_status"] == "active"
        assert r2["consecutive_failures"] == 2
        assert r2["transition"] == "failure_incremented"

        # 第 3 次失败: active → stale, consec=3
        r3 = machine.apply_run_result("src1", _run_result(fetched_count=0, status="failed"))
        assert r3["previous_status"] == "active"
        assert r3["new_status"] == "stale"
        assert r3["consecutive_failures"] == STALE_THRESHOLD
        assert r3["transition"] == "active_to_stale"
        assert r3["health_score"] == 0.5  # 3 failures

        # 验证 DB 持久化
        row = machine.get_health("src1")
        assert row["status"] == "stale"
        assert row["consecutive_failures"] == STALE_THRESHOLD

    # -------------------------------
    # 2. stale → dead (5 consecutive failures)
    # -------------------------------

    def test_stale_to_dead(self, db_conn, machine: SourceHealthMachine):
        # 起始 stale, 已连续失败 3 次
        _insert_source(db_conn, "src2", status="stale", consecutive_failures=STALE_THRESHOLD)

        # 第 4 次失败: 仍 stale, consec=4
        r1 = machine.apply_run_result("src2", _run_result(fetched_count=0, status="failed"))
        assert r1["new_status"] == "stale"
        assert r1["consecutive_failures"] == 4
        assert r1["transition"] == "failure_incremented"

        # 第 5 次失败: stale → dead, consec=5, 设置 cooldown
        r2 = machine.apply_run_result("src2", _run_result(fetched_count=0, status="failed"))
        assert r2["previous_status"] == "stale"
        assert r2["new_status"] == "dead"
        assert r2["consecutive_failures"] == DEAD_THRESHOLD
        assert r2["transition"] == "stale_to_dead"
        assert r2["health_score"] == 0.1  # 5+ failures
        assert r2["cooldown_until"] is not None  # 应设置冷却

        # 验证 DB 持久化
        row = machine.get_health("src2")
        assert row["status"] == "dead"
        assert row["consecutive_failures"] == DEAD_THRESHOLD
        assert row["cooldown_until"] is not None

    # -------------------------------
    # 3. stale → active (fetched_count > 0 resets)
    # -------------------------------

    def test_stale_to_active(self, db_conn, machine: SourceHealthMachine):
        _insert_source(db_conn, "src3", status="stale", consecutive_failures=STALE_THRESHOLD)

        r = machine.apply_run_result("src3", _run_result(fetched_count=5, status="success"))
        assert r["previous_status"] == "stale"
        assert r["new_status"] == "active"
        assert r["consecutive_failures"] == 0
        assert r["transition"] == "stale_to_active"
        assert r["health_score"] == 1.0

        row = machine.get_health("src3")
        assert row["status"] == "active"
        assert row["consecutive_failures"] == 0

    def test_stale_to_active_at_boundary(self, db_conn, machine: SourceHealthMachine):
        """stale 状态下即使只有 1 条产出也应恢复 active."""
        _insert_source(db_conn, "src-boundary", status="stale", consecutive_failures=4)

        r = machine.apply_run_result("src-boundary",
                                     _run_result(fetched_count=1, status="success"))
        assert r["new_status"] == "active"
        assert r["consecutive_failures"] == 0
        assert r["transition"] == "stale_to_active"

    # -------------------------------
    # 4. dead 状态 — 不做自动转换, 由 SourceProber 处理
    # -------------------------------

    def test_dead_no_auto_transition_with_failure(self, db_conn, machine: SourceHealthMachine):
        """dead 状态下再次失败, 不改变状态."""
        _insert_source(db_conn, "src4", status="dead", consecutive_failures=DEAD_THRESHOLD)

        r = machine.apply_run_result("src4", _run_result(fetched_count=0, status="failed"))
        assert r["previous_status"] == "dead"
        assert r["new_status"] == "dead"  # 不变
        assert r["consecutive_failures"] == DEAD_THRESHOLD  # 不变
        assert r["transition"] == "dead_no_transition"

    def test_dead_defensive_reset_on_yield(self, db_conn, machine: SourceHealthMachine):
        """dead 状态下有产出时防御性重置失败计数, 但不改变状态."""
        _insert_source(db_conn, "src4-yield", status="dead", consecutive_failures=DEAD_THRESHOLD)

        r = machine.apply_run_result("src4-yield",
                                     _run_result(fetched_count=3, status="success"))
        assert r["previous_status"] == "dead"
        assert r["new_status"] == "dead"  # 状态不变
        assert r["consecutive_failures"] == 0  # 防御性重置
        assert r["transition"] == "dead_has_yield"
        assert r["health_score"] == 1.0

    # -------------------------------
    # 5. grace → active (3 consecutive yield rounds)
    # -------------------------------

    def test_grace_to_active(self, db_conn, machine: SourceHealthMachine):
        _insert_source(db_conn, "src5", status="grace", grace_rounds=0)

        # 第 1 轮有产出: grace_rounds=1
        r1 = machine.apply_run_result("src5", _run_result(fetched_count=2, status="success"))
        assert r1["new_status"] == "grace"
        assert r1["consecutive_failures"] == 0
        assert r1["transition"] == "grace_yield_round"

        # 第 2 轮有产出: grace_rounds=2
        r2 = machine.apply_run_result("src5", _run_result(fetched_count=1, status="success"))
        assert r2["new_status"] == "grace"
        assert r2["transition"] == "grace_yield_round"

        # 第 3 轮有产出: grace → active
        r3 = machine.apply_run_result("src5", _run_result(fetched_count=3, status="success"))
        assert r3["previous_status"] == "grace"
        assert r3["new_status"] == "active"
        assert r3["consecutive_failures"] == 0
        assert r3["transition"] == "grace_to_active"
        assert r3["health_score"] == 1.0

        row = machine.get_health("src5")
        assert row["status"] == "active"
        assert row["grace_rounds"] == 0  # 已重置

    # -------------------------------
    # 6. grace → dead (3 consecutive failures in grace)
    # -------------------------------

    def test_grace_to_dead(self, db_conn, machine: SourceHealthMachine):
        _insert_source(db_conn, "src6", status="grace", consecutive_failures=0, grace_rounds=0)

        # 第 1 次失败: grace, consec=1
        r1 = machine.apply_run_result("src6", _run_result(fetched_count=0, status="failed"))
        assert r1["new_status"] == "grace"
        assert r1["consecutive_failures"] == 1
        assert r1["transition"] == "grace_failure_incremented"

        # 第 2 次失败: grace, consec=2
        r2 = machine.apply_run_result("src6", _run_result(fetched_count=0, status="failed"))
        assert r2["new_status"] == "grace"
        assert r2["consecutive_failures"] == 2
        assert r2["transition"] == "grace_failure_incremented"

        # 第 3 次失败: grace → dead, 设置 cooldown
        r3 = machine.apply_run_result("src6", _run_result(fetched_count=0, status="failed"))
        assert r3["previous_status"] == "grace"
        assert r3["new_status"] == "dead"
        assert r3["consecutive_failures"] == GRACE_FAIL_THRESHOLD
        assert r3["transition"] == "grace_to_dead"
        assert r3["health_score"] == 0.5  # 3 failures → 0.5
        assert r3["cooldown_until"] is not None

        row = machine.get_health("src6")
        assert row["status"] == "dead"
        assert row["consecutive_failures"] == GRACE_FAIL_THRESHOLD

    # -------------------------------
    # 7. disabled 跳过所有转换
    # -------------------------------

    def test_disabled_skip(self, db_conn, machine: SourceHealthMachine):
        _insert_source(db_conn, "src7", status="disabled", consecutive_failures=0)

        r = machine.apply_run_result("src7", _run_result(fetched_count=0, status="failed"))
        assert r["previous_status"] == "disabled"
        assert r["new_status"] == "disabled"
        assert r["transition"] == "disabled_skip"
        assert r["consecutive_failures"] == 0  # 不变

        # 即便有产出也保持不变
        r2 = machine.apply_run_result("src7", _run_result(fetched_count=5, status="success"))
        assert r2["new_status"] == "disabled"
        assert r2["transition"] == "disabled_skip"

    # -------------------------------
    # 补充: grace 中 partial/success 但无产出 — 不计失败
    # -------------------------------

    def test_grace_no_yield_no_fail(self, db_conn, machine: SourceHealthMachine):
        """grace 中 partial 状态但无产出不计失败."""
        _insert_source(db_conn, "src-grace-noyield", status="grace",
                       consecutive_failures=0, grace_rounds=0)

        r = machine.apply_run_result("src-grace-noyield",
                                     _run_result(fetched_count=0, status="partial"))
        assert r["new_status"] == "grace"
        assert r["consecutive_failures"] == 0  # 不计失败
        assert r["transition"] == "grace_no_yield_no_fail"

    # -------------------------------
    # 补充: active 中成功重置
    # -------------------------------

    def test_active_success_resets_failures(self, db_conn, machine: SourceHealthMachine):
        """active 状态下有产出则重置失败计数."""
        _insert_source(db_conn, "src-active-reset", status="active",
                       consecutive_failures=2)

        r = machine.apply_run_result("src-active-reset",
                                     _run_result(fetched_count=3, status="success"))
        assert r["new_status"] == "active"
        assert r["consecutive_failures"] == 0
        assert r["transition"] == "success_reset"
        assert r["health_score"] == 1.0

    # -------------------------------
    # 补充: active 中 1-2 次失败不切换状态
    # -------------------------------

    def test_active_few_failures_does_not_transition(self, db_conn, machine: SourceHealthMachine):
        """active 下 1 次 / 2 次失败仅递增计数, 不切换状态."""
        _insert_source(db_conn, "src-active-few", status="active", consecutive_failures=0)

        r1 = machine.apply_run_result("src-active-few",
                                      _run_result(fetched_count=0, status="failed"))
        assert r1["new_status"] == "active"
        assert r1["consecutive_failures"] == 1

        r2 = machine.apply_run_result("src-active-few",
                                      _run_result(fetched_count=0, status="failed"))
        assert r2["new_status"] == "active"
        assert r2["consecutive_failures"] == 2

    # -------------------------------
    # 补充: stale 中 1 次失败 (未达 DEAD_THRESHOLD) 不切换
    # -------------------------------

    def test_stale_few_failures_stays_stale(self, db_conn, machine: SourceHealthMachine):
        """stale 下失败次数 < DEAD_THRESHOLD 时保持 stale."""
        _insert_source(db_conn, "src-stale-mid", status="stale", consecutive_failures=3)

        r = machine.apply_run_result("src-stale-mid",
                                     _run_result(fetched_count=0, status="failed"))
        assert r["new_status"] == "stale"
        assert r["consecutive_failures"] == 4
        assert r["transition"] == "failure_incremented"


# ===================================================================
# 未知来源
# ===================================================================


class TestUnknownSource:
    def test_unknown_source_returns_error_dict(self, db_conn, machine: SourceHealthMachine):
        r = machine.apply_run_result("nonexistent", _run_result())
        assert r == {
            "source_id": "nonexistent",
            "previous_status": "unknown",
            "new_status": "unknown",
            "consecutive_failures": 0,
            "cooldown_until": None,
            "health_score": 0.0,
            "transition": "source_not_found",
        }


# ===================================================================
# get_health / update_health
# ===================================================================


class TestDirectMethods:
    def test_get_health_returns_row(self, db_conn, machine: SourceHealthMachine):
        _insert_source(db_conn, "get-test", name="GetTest", priority=75)
        row = machine.get_health("get-test")
        assert row is not None
        assert row["id"] == "get-test"
        assert row["name"] == "GetTest"
        assert row["priority"] == 75

    def test_get_health_nonexistent(self, db_conn, machine: SourceHealthMachine):
        assert machine.get_health("nope") is None

    def test_update_health(self, db_conn, machine: SourceHealthMachine):
        _insert_source(db_conn, "update-test", status="active")
        machine.update_health("update-test", status="stale", priority=99)
        row = machine.get_health("update-test")
        assert row["status"] == "stale"
        assert row["priority"] == 99

    def test_update_health_empty_noop(self, db_conn, machine: SourceHealthMachine):
        """不传字段不应报错."""
        _insert_source(db_conn, "noop-test")
        machine.update_health("noop-test")  # should not raise
        row = machine.get_health("noop-test")
        assert row is not None


# ===================================================================
# 健康评分写入 DB 验证
# ===================================================================


class TestHealthScorePersistence:
    def test_health_score_written_to_db(self, db_conn, machine: SourceHealthMachine):
        _insert_source(db_conn, "score-test", status="active", consecutive_failures=0)

        # 连续失败 3 次 → health_score 应为 0.5
        for _ in range(3):
            machine.apply_run_result("score-test",
                                     _run_result(fetched_count=0, status="failed"))

        row = machine.get_health("score-test")
        assert row["health_score"] == 0.5
        assert row["consecutive_failures"] == 3

    def test_health_score_improves_after_success(self, db_conn, machine: SourceHealthMachine):
        """成功抓取后健康评分回升."""
        _insert_source(db_conn, "score-recover", status="active",
                       consecutive_failures=3, health_score=0.5)

        # 原始 health_score 应为 0.5
        before = machine.get_health("score-recover")
        assert before["health_score"] == 0.5

        # 成功恢复
        machine.apply_run_result("score-recover",
                                 _run_result(fetched_count=5, status="success"))
        after = machine.get_health("score-recover")
        assert after["health_score"] == 1.0
        assert after["consecutive_failures"] == 0
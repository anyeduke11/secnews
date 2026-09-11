"""cadence 修正批 T3 — 三套健康口径对齐回归.

- T3.1 ``source_health_service._failure_rate_for_source_name``: crawler_runs.source_id
  两种口径 (批量路径写 name / tick 路径写 id) 都要匹配; 此前只按 id → 生产上 P1.7
  三档聚合永远 green (total_runs<3)。
- T3.2 ``source_revival_service.try_revive_one``: Phase 9 复活后桥接 Phase 3
  crawler_sources dead → grace, 让复活源立刻回到批量/tick 轮转漏斗。
- T3.3 ``STATUS_EQUIVALENCE`` phase3 词汇与 ``_VALID_STATUSES`` 真实枚举一致。
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.usefixtures("temp_db")


def _conn():
    from backend.repository.db import get_connection

    return get_connection()


def _insert_source(conn, sid: str, name: str, category: str, status: str = "active"):
    conn.execute(
        "INSERT INTO crawler_sources (id, category, name, kind, url, priority, enabled, status, consecutive_failures, grace_rounds) VALUES (?, ?, ?, 'html', 'https://example.com/', 50, 1, ?, 5, 2)",
        (sid, category, name, status),
    )
    conn.commit()


def _insert_run(conn, source_id: str, status: str):
    conn.execute(
        "INSERT INTO crawler_runs (source_id, category, started_at, finished_at, status, fetched_count, accepted_count, error_msg, duration_ms) VALUES (?, 'security', datetime('now'), datetime('now'), ?, 0, 0, '', 10)",
        (source_id, status),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# T3.1
# ---------------------------------------------------------------------------
def test_failure_rate_matches_name_format_runs():
    from backend.services.source_health_service import _failure_rate_for_source_name

    conn = _conn()
    _insert_source(conn, "security:x", "x", "security")
    # 批量路径口径: source_id = name
    for st in ("failed", "failed", "success"):
        _insert_run(conn, "x", st)
    out = _failure_rate_for_source_name("x")
    assert out["total_runs"] == 3 and out["failed_runs"] == 2
    assert out["status"] == "red", out


def test_failure_rate_merges_both_formats():
    from backend.services.source_health_service import _failure_rate_for_source_name

    conn = _conn()
    _insert_source(conn, "security:y", "y", "security")
    _insert_run(conn, "y", "success")             # name 口径
    _insert_run(conn, "security:y", "success")    # id 口径 (tick)
    _insert_run(conn, "security:y", "failed")
    out = _failure_rate_for_source_name("y")
    assert out["total_runs"] == 3 and out["failed_runs"] == 1
    assert out["status"] == "yellow", out  # 1/3 ≈ 0.33 ∈ [0.3, 0.6)


def test_failure_rate_unregistered_source_is_green_no_signal():
    from backend.services.source_health_service import _failure_rate_for_source_name

    out = _failure_rate_for_source_name("never-registered")
    assert out == {"status": "green", "failed_runs": 0, "total_runs": 0, "failure_rate": 0.0}


# ---------------------------------------------------------------------------
# T3.2
# ---------------------------------------------------------------------------
def test_revive_bridges_phase3_dead_to_grace():
    from backend.repository.source_stats_repo import SourceStatsRepository
    from backend.services import source_revival_service
    from backend.services.source_revival_service import try_revive_one

    conn = _conn()
    _insert_source(conn, "ai:r", "r", "ai", status="dead")
    # Phase 9 侧先有一条 dead 记录
    SourceStatsRepository().upsert_after_run("ai", "r", "https://example.com/", 0, "err")
    conn.execute("UPDATE source_stats SET status = 'dead', zero_yield_runs = 9 WHERE category = 'ai' AND source_name = 'r'")
    conn.commit()

    with patch.object(source_revival_service, "_check_url", return_value=(200, None)):
        res = try_revive_one("ai", "r", "https://example.com/", timeout_s=1.0)
    assert res.status == "revived"

    p9 = conn.execute("SELECT status FROM source_stats WHERE category = 'ai' AND source_name = 'r'").fetchone()
    assert p9["status"] == "active"
    p3 = conn.execute(
        "SELECT status, consecutive_failures, grace_rounds, cooldown_until FROM crawler_sources WHERE id = 'ai:r'"
    ).fetchone()
    assert p3["status"] == "grace", "Phase 3 必须同步 dead → grace, 否则复活源仍被排除在轮转外"
    assert (p3["consecutive_failures"], p3["grace_rounds"], p3["cooldown_until"]) == (0, 0, None)


def test_revive_failure_does_not_touch_phase3():
    from backend.services import source_revival_service
    from backend.services.source_revival_service import try_revive_one

    conn = _conn()
    _insert_source(conn, "ai:s", "s", "ai", status="dead")
    with patch.object(source_revival_service, "_check_url", return_value=(404, None)):
        res = try_revive_one("ai", "s", "https://example.com/", timeout_s=1.0)
    assert res.status != "revived"
    assert conn.execute("SELECT status FROM crawler_sources WHERE id = 'ai:s'").fetchone()["status"] == "dead"


def test_check_url_delegates_to_prober_with_ssrf_gate():
    from backend.services.source_revival_service import _check_url

    # 环回地址必须被 SSRF 门拦下 (此前 _check_url 是全仓唯一未校验的探测出口)
    code, err = _check_url("http://127.0.0.1:8000/api/health", 1.0)
    assert code == 0 and err and err.startswith("ssrf_block")


# ---------------------------------------------------------------------------
# T3.3
# ---------------------------------------------------------------------------
def test_status_equivalence_phase3_vocabulary_matches_machine():
    from backend.services.source_census_service import STATUS_EQUIVALENCE
    from backend.services.source_health_machine import _VALID_STATUSES

    listed = set()
    for tier in STATUS_EQUIVALENCE.values():
        listed.update(tier["phase3_scheduler"].split("|"))
    listed.discard("unknown")  # seed 遗留值, 不在状态机枚举里
    assert listed <= set(_VALID_STATUSES), f"phase3 词汇漂移: {listed - set(_VALID_STATUSES)}"
    assert {"active", "stale", "dead", "grace", "disabled"} <= listed
    assert datetime.now(timezone.utc).tzinfo is not None  # 防止 tz-naive 断言被静默跳过

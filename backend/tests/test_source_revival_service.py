"""v1.8 Phase 8 — source_revival_service 单测.

覆盖 (5 用例):
  - E3.1 list_dead_sources 过滤逻辑 (只列 dead + 死够久)
  - E3.2 try_revive_one 成功 (HTTP 200) → status=revived, DB 标 active
  - E3.3 try_revive_one 失败 (HTTP 4xx) → status=still_dead, DB 不变
  - E3.4 try_revive_one 网络错误 → status=error
  - E3.5 revive_all_dead 端到端 (混合: 1 revived + 1 still_dead + 1 error)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from backend.config import config
from backend.repository import db
from backend.services import source_revival_service
from backend.services.source_revival_service import (
    RevivalResult,
    list_dead_sources,
    revive_all_dead,
    try_revive_one,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path."""
    test_db = tmp_path / "test_revival.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _insert_source(
    category: str,
    source_name: str,
    source_url: str,
    status: str = "dead",
    last_checked_offset_days: int = 10,
) -> None:
    """插入一行 source_stats, last_checked_at = now - offset_days."""
    conn = db.get_connection()
    now = datetime.now(timezone.utc)
    last_checked = (now - timedelta(days=last_checked_offset_days)).isoformat()
    conn.execute(
        """
        INSERT INTO source_stats (category, source_name, source_url, status,
                                  total_runs, zero_yield_runs, total_items,
                                  last_checked_at, updated_at)
        VALUES (?, ?, ?, ?, 10, 6, 0, ?, ?)
        """,
        (category, source_name, source_url, status, last_checked, now.isoformat()),
    )


# ---------------------------------------------------------------------------
# E3.1 — list_dead_sources 过滤
# ---------------------------------------------------------------------------
def test_list_dead_sources_filters_by_status_and_age(temp_db):
    """只列 status='dead' AND last_checked_at < now - 7d 的源."""
    # 3 dead (2 死久 + 1 死新) + 1 active
    _insert_source("ai", "dead_old_1", "https://a.com/1",
                   status="dead", last_checked_offset_days=10)
    _insert_source("ai", "dead_old_2", "https://a.com/2",
                   status="dead", last_checked_offset_days=8)
    _insert_source("ai", "dead_new", "https://a.com/3",
                   status="dead", last_checked_offset_days=2)  # 死不够久
    _insert_source("ai", "alive", "https://a.com/4",
                   status="active", last_checked_offset_days=1)

    rows = list_dead_sources(dead_for_days=7)
    names = {r["source_name"] for r in rows}
    assert names == {"dead_old_1", "dead_old_2"}
    # 验证 category 也对
    assert all(r["category"] == "ai" for r in rows)


# ---------------------------------------------------------------------------
# E3.2 — try_revive_one 成功
# ---------------------------------------------------------------------------
def test_try_revive_one_success_revives_source(temp_db):
    """HTTP 200 → status=revived + DB status='active'."""
    _insert_source("ai", "test_revive_ok", "https://a.com/ok",
                   status="dead", last_checked_offset_days=8)

    with patch.object(source_revival_service, "_check_url", return_value=(200, None)):
        result = try_revive_one("ai", "test_revive_ok", "https://a.com/ok", timeout_s=1.0)

    assert isinstance(result, RevivalResult)
    assert result.status == "revived"
    assert result.http_code == 200
    # DB 状态应是 active
    conn = db.get_connection()
    row = conn.execute(
        "SELECT status, zero_yield_runs FROM source_stats "
        "WHERE category='ai' AND source_name='test_revive_ok'"
    ).fetchone()
    assert row["status"] == "active"
    assert int(row["zero_yield_runs"]) == 0


# ---------------------------------------------------------------------------
# E3.3 — try_revive_one 4xx
# ---------------------------------------------------------------------------
def test_try_revive_one_4xx_keeps_dead(temp_db):
    """HTTP 404 → status=still_dead + DB 仍为 dead."""
    _insert_source("ai", "test_404", "https://a.com/missing",
                   status="dead", last_checked_offset_days=8)

    with patch.object(source_revival_service, "_check_url", return_value=(404, None)):
        result = try_revive_one("ai", "test_404", "https://a.com/missing", timeout_s=1.0)

    assert result.status == "still_dead"
    assert result.http_code == 404
    # DB 仍为 dead
    conn = db.get_connection()
    row = conn.execute(
        "SELECT status FROM source_stats "
        "WHERE category='ai' AND source_name='test_404'"
    ).fetchone()
    assert row["status"] == "dead"


# ---------------------------------------------------------------------------
# E3.4 — try_revive_one 网络错误
# ---------------------------------------------------------------------------
def test_try_revive_one_network_error(temp_db):
    """网络异常 → status=error."""
    _insert_source("ai", "test_neterr", "https://a.com/down",
                   status="dead", last_checked_offset_days=8)

    with patch.object(
        source_revival_service, "_check_url",
        return_value=(0, "URLError: timeout"),
    ):
        result = try_revive_one("ai", "test_neterr", "https://a.com/down", timeout_s=1.0)

    assert result.status == "error"
    assert "timeout" in (result.error_msg or "")


# ---------------------------------------------------------------------------
# E3.5 — revive_all_dead 端到端
# ---------------------------------------------------------------------------
def test_revive_all_dead_end_to_end(temp_db):
    """混合: 1 revived + 1 still_dead + 1 error."""
    _insert_source("ai", "ok_one", "https://a.com/ok",
                   status="dead", last_checked_offset_days=10)
    _insert_source("ai", "bad_one", "https://a.com/bad",
                   status="dead", last_checked_offset_days=10)
    _insert_source("ai", "err_one", "https://a.com/err",
                   status="dead", last_checked_offset_days=10)

    def fake_check(url: str, timeout: float):
        if "ok" in url:
            return 200, None
        if "bad" in url:
            return 503, None  # 5xx → still_dead
        return 0, "URLError: refused"

    with patch.object(source_revival_service, "_check_url", side_effect=fake_check):
        results = revive_all_dead(dead_for_days=7, timeout_s=1.0)

    assert len(results) == 3
    by_name = {r.source_name: r for r in results}
    assert by_name["ok_one"].status == "revived"
    assert by_name["bad_one"].status == "still_dead"
    assert by_name["err_one"].status == "error"

    # 验证 DB 状态
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT source_name, status FROM source_stats "
        "WHERE category='ai' ORDER BY source_name"
    ).fetchall()
    by_name_db = {r["source_name"]: r["status"] for r in rows}
    assert by_name_db["ok_one"] == "active"
    assert by_name_db["bad_one"] == "dead"
    assert by_name_db["err_one"] == "dead"

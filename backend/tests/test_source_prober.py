"""采集闭环 T1/T3 — source_prober 探测口径 + 失效源自动退役闭环测试.

覆盖:
- T1: 探测 alive 零产出不抬 last_yield_at / 有产出才抬 / last_error NULL
- T3: dead>14d 探测失败自动退役 / 13d 不退役 / retired 低频探测 /
      探测成功复活 / source_alerts 去重 bump
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.db import get_connection

# ---------------------------------------------------------------------------
# Fixtures — 隔离 DB 到 tmp_path (真实 migration schema, 同 test_source_alerter)
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 DB 到 tmp_path."""
    test_db = tmp_path / "test_source_prober.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def head_status(monkeypatch: pytest.MonkeyPatch):
    """可控的 _head_status 桩: responses dict 映射 source_id → (code, err)."""
    import backend.services.source_prober as prober_mod

    responses: dict[str, tuple[int, str | None]] = {}

    def _fake_head(url: str, t: int) -> tuple[int, str | None]:
        return responses.get(_url_owner(url), (200, None))

    monkeypatch.setattr(prober_mod, "_head_status", _fake_head)

    class _Stub:
        def set(self, source_id: str, code: int, err: str | None = None) -> None:
            responses[source_id] = (code, err)

    return _Stub()


_URL_OWNERS: dict[str, str] = {}


def _url_owner(url: str) -> str:
    return _URL_OWNERS.get(url, "unknown")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_source(
    source_id: str,
    *,
    status: str = "dead",
    enabled: int = 1,
    name: str = "",
    last_success_at: str | None = None,
    last_yield_at: str | None = None,
    cooldown_until: str | None = None,
    url: str = "",
) -> None:
    """插入 crawler_sources 行 (探测域), 并登记 URL→id 映射供 HEAD 桩路由."""
    if not name:
        name = source_id
    probe_url = url or f"https://example.com/{source_id}/feed"
    _URL_OWNERS[probe_url] = source_id
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO crawler_sources
            (id, category, name, kind, url, feed_url, status, enabled,
             consecutive_failures, health_score, last_success_at, last_yield_at,
             cooldown_until, created_at, updated_at)
        VALUES (?, 'ai', ?, 'rss', ?, ?, ?, ?,
                5, 0.1, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (source_id, name, probe_url, probe_url, status, enabled,
         last_success_at, last_yield_at, cooldown_until),
    )


def _get_source(source_id: str) -> dict:
    row = get_connection().execute(
        "SELECT * FROM crawler_sources WHERE id = ?", (source_id,)
    ).fetchone()
    assert row is not None, f"source {source_id} missing"
    return dict(row)


def _days_ago_iso(days: float) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat()


def _probe(source_id: str, **kwargs):
    from backend.services.source_prober import probe_one

    return probe_one(source_id, **kwargs)


# ===================================================================
# T1 — yield 口径
# ===================================================================


class TestProbeYieldSemantics:
    def test_probe_alive_zero_yield_keeps_last_yield_at(self, temp_db, head_status):
        """探测连通但零产出 → 回 grace 但不动 last_yield_at (病灶: 探测污染 yield)."""
        _insert_source(
            "p-zero", status="dead",
            last_yield_at="2020-01-01T00:00:00+00:00",
            last_success_at="2020-01-01T00:00:00+00:00",
        )
        head_status.set("p-zero", 200, None)
        result = _probe("p-zero")
        assert result.status == "alive"
        assert result.new_status == "grace"
        row = _get_source("p-zero")
        assert row["status"] == "grace"
        assert row["consecutive_failures"] == 0
        assert row["last_yield_at"] == "2020-01-01T00:00:00+00:00"
        assert row["last_success_at"] == "2020-01-01T00:00:00+00:00"

    def test_probe_alive_with_items_bumps_yield(self, temp_db, head_status):
        """探测运行有真实条目入库 (produced_items>0) → 抬 yield/success。"""
        _insert_source("p-yield", status="dead", last_yield_at=None)
        head_status.set("p-yield", 200, None)
        result = _probe("p-yield", produced_items=5)
        assert result.status == "alive"
        row = _get_source("p-yield")
        assert row["last_yield_at"] is not None
        assert row["last_success_at"] is not None

    def test_probe_alive_clears_last_error_to_null(self, temp_db, head_status):
        """探测成功 → last_error 存 NULL 而非空字符串。"""
        _insert_source("p-err", status="dead")
        get_connection().execute(
            "UPDATE crawler_sources SET last_error = 'HTTP 503' WHERE id = 'p-err'"
        )
        head_status.set("p-err", 200, None)
        _probe("p-err")
        row = _get_source("p-err")
        assert row["last_error"] is None

    def test_probe_dead_keeps_error(self, temp_db, head_status):
        """探测失败 → 保留 dead + 写真实错误。"""
        _insert_source("p-dead", status="dead")
        head_status.set("p-dead", 0, "URLError: conn refused")
        result = _probe("p-dead")
        assert result.status == "dead"
        assert result.new_status == "dead"
        row = _get_source("p-dead")
        assert row["status"] == "dead"
        assert "conn refused" in (row["last_error"] or "")

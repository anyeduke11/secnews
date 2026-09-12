"""health_query_service 单测 (Batch 2 SQL 下沉).

覆盖:
  - hotspots_row_count / db_health (空表检测 = chaos truncate 场景)
  - db_integrity 60s TTL 缓存
  - stats_hotspots_total / collect_stats_24h / last_fallback_at
    (预建 warm.db 使 `warm.collection_runs` ATTACH 生效, 走真实 SQL)
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.services import health_query_service as hqs

_WARM_SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT    NOT NULL,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT,
    status          TEXT    NOT NULL,
    item_count      INTEGER NOT NULL DEFAULT 0,
    fallback_count  INTEGER NOT NULL DEFAULT 0,
    error_msg       TEXT,
    duration_ms     INTEGER
);
"""


def _insert_run(category: str, started_at: str, status: str, duration_ms: int,
                fallback_count: int = 0) -> None:
    db.get_connection().execute(
        "INSERT INTO warm.collection_runs "
        "(category, started_at, status, item_count, fallback_count, duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (category, started_at, status, 1, fallback_count, duration_ms),
    )


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """隔离 hot + warm 两个 DB 文件; warm 文件预建使 ATTACH 成功."""
    test_db = tmp_path / "test_health_query_service.db"
    warm_db = tmp_path / "test-warm.db"
    _w = sqlite3.connect(str(warm_db))
    _w.executescript(_WARM_SCHEMA)
    _w.commit()
    _w.close()

    monkeypatch.setattr(config, "db_path", test_db)
    monkeypatch.setattr(config, "warm_db_path", warm_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture(autouse=True)
def _reset_integrity_cache():
    """integrity TTL 缓存是模块级状态, 每用例前清空防跨测试污染."""
    hqs._INTEGRITY_CACHE.pop("result", None)
    yield
    hqs._INTEGRITY_CACHE.pop("result", None)


def _insert_hotspot(hid: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.get_connection().execute(
        "INSERT INTO hotspots (id, title, source, url, category, "
        "published_at, score, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (hid, f"title-{hid}", "test", f"https://example.com/{hid}",
         "security", now, 80, now),
    )
    db.get_connection().commit()


def test_hotspots_row_count_empty_and_seeded(temp_db):
    # 全新库 hotspots 为空 → 0 (db_health 将视为损坏)
    assert hqs.hotspots_row_count() == 0
    _insert_hotspot("h-1")
    assert hqs.hotspots_row_count() == 1


def test_db_health_flags_empty_hotspots(temp_db):
    data = hqs.db_health()
    assert data["ok"] is False
    assert data["hotspots_count"] == 0
    assert "hotspots table is empty" in data["error"]
    for key in ("latency_ms", "size_mb", "wal", "integrity"):
        assert key in data


def test_db_health_ok_with_rows(temp_db):
    _insert_hotspot("h-1")
    data = hqs.db_health()
    assert data["ok"] is True
    assert data["hotspots_count"] == 1
    assert data["wal"]["mode"] in ("wal", "delete", "memory")


def test_db_integrity_ttl_cache(temp_db):
    first = hqs.db_integrity()
    assert first == {"ok": True, "result": "ok"}
    second = hqs.db_integrity()
    assert second == first
    assert hqs._INTEGRITY_CACHE["result"]["ts"] > 0


def test_collect_stats_24h_and_last_fallback(temp_db):
    now = datetime.now(timezone.utc)
    _insert_run("ai", (now - timedelta(hours=1)).isoformat(), "success", 1200)
    _insert_run("security", (now - timedelta(hours=2)).isoformat(), "success", 800,
                fallback_count=2)
    # 30h 前 → 不进 24h 窗口
    _insert_run("ai", (now - timedelta(hours=30)).isoformat(), "failed", 500)
    db.get_connection().commit()

    stats = hqs.collect_stats_24h()
    assert stats["collect_runs_24h"] == 2
    assert stats["success_rate_24h"] == 1.0
    assert stats["avg_collect_duration_ms"] == 1000

    assert hqs.last_fallback_at() is not None
    assert hqs.stats_hotspots_total() == 0

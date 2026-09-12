"""attention_events_service 单测 (Batch 2 SQL 下沉).

覆盖:
  - record_event: 写入 + 返回 lastrowid
  - heatmap_by_day_hour: 天×小时聚合 + days 截断
  - maybe_create_sm2_review: dwell<=30 不转化 / view 命中知识条目转化 /
    未知 item 静默跳过
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.services import attention_events_service as aes


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_attention_events_service.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _insert_knowledge_item(item_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = db.get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO knowledge_items
            (id, title, source, domain, topic, type, difficulty, tags, concepts,
             mastery, compiled, ingested_at, updated_at, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (item_id, f"Item {item_id}", "test", "security", "", "article",
         "beginner", "[]", "[]", 0, 0, now, now,
         f"https://example.com/{item_id}"),
    )
    conn.commit()


def test_record_event_inserts_and_returns_id(temp_db):
    _insert_knowledge_item("item-1")
    event_id = aes.record_event("item-1", "view", {"foo": "bar"})
    row = db.get_connection().execute(
        "SELECT * FROM attention_events WHERE id = ?", (event_id,)
    ).fetchone()
    assert row is not None
    assert row["item_id"] == "item-1"
    assert row["event_type"] == "view"
    assert '"foo"' in row["detail_json"]


def test_heatmap_aggregates_by_day_hour(temp_db):
    _insert_knowledge_item("item-1")
    aes.record_event("item-1", "view", {})
    aes.record_event("item-1", "view", {})
    # 手工插入一条 3 天前的事件 (应被 days=1 截断, days=30 命中)
    old = "2020-01-01T05:30:00+00:00"
    db.get_connection().execute(
        "INSERT INTO attention_events (item_id, event_type, detail_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        ("item-1", "dwell", "{}", old),
    )
    db.get_connection().commit()

    events = aes.heatmap_by_day_hour(days=30)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    hour = datetime.now(timezone.utc).hour
    # 2020-01-01 的事件也命中 days=30? 不 — 2020 距今超过 30 天, 被截断
    buckets = {(e["date"], e["hour"]): e["count"] for e in events}
    assert buckets.get((today, hour)) == 2
    assert ("2020-01-01", 5) not in buckets

    for e in events:
        assert set(e.keys()) == {"date", "hour", "count"}
        assert 0 <= e["hour"] <= 23


def test_maybe_create_sm2_review_dwell_under_threshold_skipped(temp_db):
    _insert_knowledge_item("item-1")
    aes.maybe_create_sm2_review("dwell", "item-1", {"dwell_seconds": 30})
    assert db.get_connection().execute(
        "SELECT COUNT(*) AS n FROM sm2_reviews"
    ).fetchone()["n"] == 0


def test_maybe_create_sm2_review_view_converts(temp_db):
    _insert_knowledge_item("item-1")
    aes.maybe_create_sm2_review("view", "item-1", {})
    assert db.get_connection().execute(
        "SELECT COUNT(*) AS n FROM sm2_reviews"
    ).fetchone()["n"] == 1


def test_maybe_create_sm2_review_unknown_item_skipped(temp_db):
    # item 不在 knowledge_items → 静默跳过, 不抛异常
    aes.maybe_create_sm2_review("view", "no-such-item", {})
    assert db.get_connection().execute(
        "SELECT COUNT(*) AS n FROM sm2_reviews"
    ).fetchone()["n"] == 0

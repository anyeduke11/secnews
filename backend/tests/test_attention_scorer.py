"""Phase 17 — Attention Scorer 服务测试。

覆盖 (5 用例):
  - score() 返回 0-100 整数
  - score() 仅 view 事件
  - score() 含 dwell 事件
  - score() 含 favorited 条目
  - batch_score() 更新所有条目
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.config import config
from backend.repository import db
from backend.services import attention_scorer


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_attention_scorer.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


def _insert_knowledge_item(item_id: str, source_url: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = db.get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO knowledge_items
            (id, title, source, domain, topic, type, difficulty, tags, concepts,
             mastery, compiled, ingested_at, updated_at, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (item_id, f"Item {item_id}", "test", "security", "", "article", "beginner",
         "[]", "[]", 0, 0, now, now, source_url or f"https://example.com/{item_id}"),
    )


def _insert_attention_event(item_id: str, event_type: str, detail: dict | None = None) -> None:
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO attention_events (item_id, event_type, detail_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (item_id, event_type, json.dumps(detail or {}), datetime.now(timezone.utc).isoformat()),
    )


def _insert_favorite(url: str) -> None:
    from backend.repository.db import get_connection

    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO favorites (hotspot_id, category, title, source, url, favorited_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("h-1", "security", "Test", "test", url, datetime.now(timezone.utc).isoformat()),
    )


# ===========================================================================
# 1. score()
# ===========================================================================
class TestScore:
    def test_score_returns_zero_to_hundred_int(self, temp_db):
        _insert_knowledge_item("k-s-0")
        s = attention_scorer.score("k-s-0")
        assert isinstance(s, int)
        assert 0 <= s <= 100

    def test_score_with_view_events_only(self, temp_db):
        _insert_knowledge_item("k-s-view")
        # 10 view events
        for _ in range(10):
            _insert_attention_event("k-s-view", "view")
        s = attention_scorer.score("k-s-view")
        # view 权重 0.25, 10/20 * 0.25 * 100 = 12.5 → 13 or 12
        assert s > 0
        assert s <= 100

    def test_score_with_dwell_events(self, temp_db):
        _insert_knowledge_item("k-s-dwell")
        # 150 seconds dwell
        _insert_attention_event("k-s-dwell", "dwell", {"dwell_seconds": 150})
        s = attention_scorer.score("k-s-dwell")
        # dwell 权重 0.25, 150/300 * 0.25 * 100 = 12.5 → 13 or 12
        assert s > 0
        assert s <= 100

    def test_score_with_favorited_item(self, temp_db):
        url = "https://example.com/k-s-fav"
        _insert_knowledge_item("k-s-fav", source_url=url)
        _insert_favorite(url)
        s = attention_scorer.score("k-s-fav")
        # is_favorited 权重 0.20 → at least 20
        assert s >= 20


# ===========================================================================
# 2. batch_score()
# ===========================================================================
class TestBatchScore:
    def test_batch_score_updates_all_items(self, temp_db):
        _insert_knowledge_item("k-b-1")
        _insert_knowledge_item("k-b-2")
        _insert_knowledge_item("k-b-3")

        result = attention_scorer.batch_score()
        assert result["updated"] == 3
        assert result["errors"] == 0

        # Verify attention_score was set in DB
        conn = db.get_connection()
        rows = conn.execute(
            "SELECT id, attention_score FROM knowledge_items ORDER BY id"
        ).fetchall()
        scores = {r["id"]: r["attention_score"] for r in rows}
        assert "k-b-1" in scores
        assert "k-b-2" in scores
        assert "k-b-3" in scores
        for sid in ("k-b-1", "k-b-2", "k-b-3"):
            assert 0 <= scores[sid] <= 100
"""v0.7 Batch ⑤ — FeedbackService 测试.

覆盖:
- submit_feedback: like/dislike 信号、权重更新、持久化
- get_entity_feedback: 按实体查询
- get_feedback_profile: 画像摘要
- 非法 action 校验
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.feedback_repo import FeedbackRepository
from backend.services import profile_service
from backend.services.feedback_service import FeedbackService


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_feedback.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def svc(temp_db):
    return FeedbackService()


def _insert_hotspot(hotspot_id: str, title: str = "Test", category: str = "ai", source: str = "test"):
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    from backend.repository.db import get_connection
    get_connection().execute(
        """
        INSERT OR REPLACE INTO hotspots
            (id, title, summary, source, url, category, published_at, score,
             fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hotspot_id, title, "summary", source,
            f"https://example.com/{hotspot_id}", category, now, 50.0,
            now, 0, 80, "[]", "pending", now,
        ),
    )


class TestSubmitFeedback:
    def test_like_returns_positive_signal(self, svc):
        result = svc.submit_feedback("hotspot", "h-1", "like")
        assert result["ok"] is True
        assert result["action"] == "like"
        assert result["signal"] == profile_service.SIGNAL_LIKE
        assert result["signal"] > 0

    def test_dislike_returns_negative_signal(self, svc):
        result = svc.submit_feedback("hotspot", "h-1", "dislike")
        assert result["ok"] is True
        assert result["action"] == "dislike"
        assert result["signal"] == profile_service.SIGNAL_DISLIKE
        assert result["signal"] < 0

    def test_like_stronger_than_favorite(self, svc):
        assert profile_service.SIGNAL_LIKE > profile_service.SIGNAL_FAVORITE

    def test_dislike_stronger_than_skip(self, svc):
        assert abs(profile_service.SIGNAL_DISLIKE) > abs(profile_service.SIGNAL_SKIP)

    def test_invalid_action_raises(self, svc):
        with pytest.raises(ValueError, match="invalid action"):
            svc.submit_feedback("hotspot", "h-1", "neutral")

    def test_like_persists_event(self, svc):
        result = svc.submit_feedback("hotspot", "h-1", "like")
        event_id = result["event_id"]
        assert event_id is not None
        repo = FeedbackRepository()
        row = repo.get_by_entity("hotspot", "h-1")
        assert len(row) == 1
        assert row[0]["id"] == event_id
        assert row[0]["action"] == "like"

    def test_dislike_persists_event(self, svc):
        result = svc.submit_feedback("hotspot", "h-1", "dislike")
        event_id = result["event_id"]
        assert event_id is not None
        repo = FeedbackRepository()
        row = repo.get_by_entity("hotspot", "h-1")
        assert len(row) == 1
        assert row[0]["action"] == "dislike"

    def test_like_updates_profile_weight(self, svc, temp_db):
        _insert_hotspot("h-1", category="ai", source="test")
        result = svc.submit_feedback("hotspot", "h-1", "like")
        weights = result["weights"]
        assert "category:ai" in weights
        assert weights["category:ai"] > 0
        assert "source:test" in weights
        assert weights["source:test"] > 0

    def test_dislike_lowers_weight(self, svc, temp_db):
        _insert_hotspot("h-1", category="ai", source="test")
        # First set a positive weight
        profile_service.apply_signal("category:ai", profile_service.SIGNAL_FAVORITE)
        before = profile_service.get_weight("category:ai")
        svc.submit_feedback("hotspot", "h-1", "dislike")
        after = profile_service.get_weight("category:ai")
        assert after < before

    def test_missing_entity_no_profile_update(self, svc):
        result = svc.submit_feedback("hotspot", "nonexistent", "like")
        assert result["ok"] is True
        assert result["weights"] == {}

    def test_feedback_profile_summary(self, svc):
        svc.submit_feedback("hotspot", "h-1", "like")
        svc.submit_feedback("hotspot", "h-2", "dislike")
        profile = svc.get_feedback_profile()
        assert profile["total_likes"] >= 1
        assert profile["total_dislikes"] >= 1
        assert len(profile["recent"]) == 2


class TestEntityFeedbackHistory:
    def test_get_entity_feedback_empty(self, svc):
        result = svc.get_entity_feedback("hotspot", "nonexistent")
        assert result == []

    def test_get_entity_feedback_ordered(self, svc):
        svc.submit_feedback("hotspot", "h-1", "like")
        svc.submit_feedback("hotspot", "h-1", "dislike")
        history = svc.get_entity_feedback("hotspot", "h-1")
        assert len(history) == 2
        assert history[0]["action"] == "like"
        assert history[1]["action"] == "dislike"

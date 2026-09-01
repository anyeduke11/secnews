"""v0.7 Batch ⑤ — FeedbackAnalyzer + UserMemoryService 测试.

覆盖:
- FeedbackAnalyzer.analyze_batch: 空批次、LLM 返回 JSON、记忆写入
- UserMemoryService: 写入/读取/列表/上下文聚合
"""
from __future__ import annotations

import json

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.feedback_repo import FeedbackRepository
from backend.services.feedback_analyzer import FeedbackAnalyzer
from backend.services.user_memory_service import UserMemoryService


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_feedback_analyzer.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def analyzer(temp_db):
    return FeedbackAnalyzer()


def _insert_feedback(category="ai", source="test", tags=None):
    repo = FeedbackRepository()
    return repo.record(
        entity_type="hotspot",
        entity_id="h-1",
        action="like",
        signal=0.4,
        category=category,
        source=source,
        tags=tags or ["vulnerability"],
        title="Test",
    )


class TestFeedbackAnalyzer:
    def test_empty_batch_returns_noop(self, analyzer):
        result = analyzer.analyze_batch(batch_size=20)
        assert result["ok"] is True
        assert result["analyzed"] == 0
        assert result["memory_keys"] == []

    def test_analyze_batch_with_llm_mock(self, analyzer, temp_db, monkeypatch):
        _insert_feedback()
        mock_response = json.dumps({
            "interests": ["ai", "vulnerability"],
            "dislikes": ["noise"],
            "preferred_sources": ["test"],
            "reading_style": "deep",
            "confidence": 0.9,
            "summary": "AI 安全爱好者"
        })
        call_count = [0]

        async def mock_generate(prompt, **kwargs):
            call_count[0] += 1
            return mock_response

        monkeypatch.setattr("backend.services.ai_hub.llm_service.generate", mock_generate)

        result = analyzer.analyze_batch(batch_size=20)
        assert result["ok"] is True
        assert result["analyzed"] == 1
        assert len(result["memory_keys"]) > 0
        assert call_count[0] >= 1
        assert call_count[0] >= 1


class TestUserMemoryService:
    def test_record_and_get_memory(self, temp_db):
        svc = UserMemoryService()
        row = svc.record_memory("interest", "ai", '{"source":"test"}')
        assert row["memory_type"] == "interest"
        assert row["key"] == "ai"

        got = svc.get_memory("interest", "ai")
        assert got is not None
        assert got["value"] == '{"source":"test"}'

    def test_upsert_updates_existing(self, temp_db):
        svc = UserMemoryService()
        svc.record_memory("interest", "ai", '{"v":1}')
        svc.record_memory("interest", "ai", '{"v":2}')
        got = svc.get_memory("interest", "ai")
        assert got["value"] == '{"v":2}'

    def test_list_by_type(self, temp_db):
        svc = UserMemoryService()
        svc.record_memory("interest", "ai", "{}")
        svc.record_memory("interest", "sec", "{}")
        svc.record_memory("dislike", "noise", "{}")
        interests = svc.list_memories("interest")
        assert len(interests) == 2

    def test_get_user_context(self, temp_db):
        svc = UserMemoryService()
        svc.record_memory("interest", "ai", '{"interest":"ai"}')
        svc.record_memory("dislike", "noise", '{"dislike":"noise"}')
        svc.record_memory("source_pref", "test", '{"preferred_source":"test"}')
        ctx = svc.get_user_context()
        assert "ai" in ctx["interests"]
        assert "noise" in ctx["dislikes"]
        assert "test" in ctx["source_prefs"]
        assert ctx["raw_count"] == 3
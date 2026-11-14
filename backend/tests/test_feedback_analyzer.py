"""v0.7 Batch ⑤ — UserMemoryService 测试 (R-16: FeedbackAnalyzer 孤儿 service 已删除).

覆盖:
- UserMemoryService: 写入/读取/列表/上下文聚合
"""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db
from backend.services.user_memory_service import UserMemoryService


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_feedback_analyzer.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


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
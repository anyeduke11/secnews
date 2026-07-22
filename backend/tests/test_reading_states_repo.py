"""ReadingStateRepository 单元测试 — 打开次数 + 停留时长 + 最近列表."""
from __future__ import annotations

import pytest

from backend.config import config
from backend.repository import db
from backend.repository.reading_states_repo import ReadingStateRepository


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_rs.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def repo(temp_db):
    return ReadingStateRepository()


class TestReadingState:
    def test_record_open_increments_count(self, repo):
        """首次打开: opened_count=1."""
        repo.record_open("hotspot", "h1")
        state = repo.get("hotspot", "h1")
        assert state is not None
        assert state.opened_count == 1
        assert state.dwell_ms == 0
        assert state.last_read_at is not None

    def test_record_open_multiple_times(self, repo):
        """多次打开: opened_count 累加."""
        for _ in range(3):
            repo.record_open("hotspot", "h2")
        state = repo.get("hotspot", "h2")
        assert state is not None
        assert state.opened_count == 3

    def test_record_dwell_accumulates(self, repo):
        """停留时长累加, 不影响 opened_count."""
        repo.record_dwell("hotspot", "h3", 1000)
        repo.record_dwell("hotspot", "h3", 2500)
        state = repo.get("hotspot", "h3")
        assert state is not None
        assert state.dwell_ms == 3500
        assert state.opened_count == 0  # dwell 不改 opened_count

    def test_record_open_and_dwell_combined(self, repo):
        """打开 + 停留混合."""
        repo.record_open("knowledge", "k1")
        repo.record_dwell("knowledge", "k1", 5000)
        repo.record_open("knowledge", "k1")
        state = repo.get("knowledge", "k1")
        assert state is not None
        assert state.opened_count == 2
        assert state.dwell_ms == 5000

    def test_get_nonexistent_returns_none(self, repo):
        assert repo.get("hotspot", "nope") is None

    def test_list_recent_orders_by_last_read_desc(self, repo):
        """最近列表按 last_read_at 倒序."""
        repo.record_open("hotspot", "old")
        repo.record_open("hotspot", "new")
        # 再 open 一次 new, 让它的 last_read_at 更晚
        repo.record_open("hotspot", "new")
        recent = repo.list_recent(entity_type="hotspot")
        # new 应该排在 old 前面 (last_read_at 更晚)
        assert recent[0].entity_id == "new"
        assert recent[1].entity_id == "old"
        assert recent[0].opened_count == 2

    def test_list_recent_filters_by_entity_type(self, repo):
        repo.record_open("hotspot", "h-x")
        repo.record_open("knowledge", "k-x")
        hotspot_only = repo.list_recent(entity_type="hotspot")
        assert all(s.entity_type == "hotspot" for s in hotspot_only)
        assert len(hotspot_only) == 1

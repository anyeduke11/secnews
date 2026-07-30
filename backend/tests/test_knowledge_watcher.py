"""Knowledge watcher tests — conflict detection, debounce, publish status sync.

Most watcher logic is event-driven (file system events). These tests
focus on the detect-and-conflict logic that can be tested in isolation.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock

import pytest

from backend.services.knowledge_watcher import (
    _CONFLICT_WINDOW_SECONDS,
    _COOLDOWN_SECONDS,
    _DEBOUNCE_SECONDS,
    _KnowledgeEventHandler,
    _maybe_sync_publish_status,
    _maybe_update_map,
    CONFLICTS_DIR,
)


# ---------------------------------------------------------------------------
# _KnowledgeEventHandler
# ---------------------------------------------------------------------------

class TestConflictDetection:
    """Test the conflict detection logic in _KnowledgeEventHandler."""

    @pytest.fixture(autouse=True)
    def _isolate_conflicts(self, tmp_path: Path, monkeypatch):
        """隔离 CONFLICTS_DIR 到临时目录。

        真实 knowledge/.conflicts/ 已有历史冲突文件, 断言全局目录为空会误判;
        patch 到独立 tmp 目录, 让断言只反映本测试 handler 是否创建了新冲突。
        """
        import backend.services.knowledge_watcher as kw
        d = tmp_path / ".conflicts_isolated"
        monkeypatch.setattr(kw, "CONFLICTS_DIR", d)
        self._conflicts_dir = d

    def make_handler(self, subdir: str = "items") -> _KnowledgeEventHandler:
        return _KnowledgeEventHandler(subdir)

    def test_no_conflict_first_event(self, tmp_path: Path):
        """First event never triggers conflict."""
        handler = self.make_handler()
        f = tmp_path / "test.md"
        f.write_text("content", encoding="utf-8")
        handler._handle(str(f))
        # No conflict recorded
        assert not list(self._conflicts_dir.glob("*"))

    def test_no_conflict_same_content(self, tmp_path: Path):
        """Same content within window → no conflict (duplicate event)."""
        handler = self.make_handler()
        f = tmp_path / "test.md"
        f.write_text("content", encoding="utf-8")
        handler._handle(str(f))
        f.write_text("content", encoding="utf-8")  # Same content
        handler._handle(str(f))
        assert not list(self._conflicts_dir.glob("*"))

    def test_no_conflict_outside_window(self, tmp_path: Path):
        """Different content but outside window → no conflict."""
        handler = self.make_handler()
        f = tmp_path / "test.md"
        f.write_text("v1", encoding="utf-8")
        handler._handle(str(f))
        # Simulate time passing beyond window
        handler._last_mod[str(f)] = (time.time() - _CONFLICT_WINDOW_SECONDS - 0.1, "v1")
        f.write_text("v2", encoding="utf-8")
        handler._handle(str(f))
        assert not list(self._conflicts_dir.glob("*"))

    def test_skips_non_md_files(self, tmp_path: Path):
        """Non .md files are skipped."""
        handler = self.make_handler()
        f = tmp_path / "test.txt"
        f.write_text("content", encoding="utf-8")
        handler._handle(str(f))
        # Should not track .txt files
        assert str(f) not in handler._last_mod

    def test_cooldown_conflict_appends_rollup(self, tmp_path: Path):
        """冷却期内的真实冲突不再静默丢弃 — 追加到 rollup 文件。"""
        handler = self.make_handler()
        f = tmp_path / "test.md"
        # 第一次冲突: 生成独立快照 + 进入冷却期
        f.write_text("v1", encoding="utf-8")
        handler._handle(str(f))
        f.write_text("v2", encoding="utf-8")
        handler._handle(str(f))
        snapshots = list(self._conflicts_dir.glob("test.conflict-2*.md"))
        assert len(snapshots) == 1
        # 冷却期内的后续冲突: 不新建快照, 追加到 rollup
        f.write_text("v3", encoding="utf-8")
        handler._handle(str(f))
        f.write_text("v4", encoding="utf-8")
        handler._handle(str(f))
        assert len(list(self._conflicts_dir.glob("test.conflict-2*.md"))) == 1
        rollup = self._conflicts_dir / "test.conflict-rollup.md"
        assert rollup.exists()
        content = rollup.read_text(encoding="utf-8")
        # 被覆盖的 v2/v3 都在 rollup 里 (不丢数据)
        assert "v2" in content
        assert "v3" in content
        assert content.count("rollup: true") == 2


# ---------------------------------------------------------------------------
# Publish status sync
# ---------------------------------------------------------------------------

class TestMaybeSyncPublishStatus:
    """Test _maybe_sync_publish_status parsing logic."""

    def test_skips_non_task_files(self, tmp_path: Path):
        """Non-task file paths are skipped."""
        # Just ensure no exception is raised
        _maybe_sync_publish_status(str(tmp_path / "readme.md"))

    def test_skips_pending_and_processing(self, tmp_path: Path):
        """Files in pending/ or processing/ are skipped."""
        pending = tmp_path / "tasks" / "pending" / "task-1.md"
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text("---\ntask_type: compile\n---\nbody", encoding="utf-8")
        # Should not raise
        _maybe_sync_publish_status(str(pending))


# ---------------------------------------------------------------------------
# _maybe_update_map
# ---------------------------------------------------------------------------

class TestMaybeUpdateMap:
    """Test _maybe_update_map task type detection."""

    def test_skips_non_task(self, tmp_path: Path):
        """Non-task file path is skipped."""
        _maybe_update_map(str(tmp_path / "readme.md"))

    def test_skips_pending_compile(self, tmp_path: Path):
        """Pending compile task is skipped."""
        pending = tmp_path / "tasks" / "pending" / "task-1.md"
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text("---\ntask_type: compile\n---\nbody", encoding="utf-8")
        _maybe_update_map(str(pending))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify configuration constants are reasonable."""

    def test_window_greater_than_debounce(self):
        """Conflict window should be wider than debounce to avoid false positives."""
        assert _CONFLICT_WINDOW_SECONDS > _DEBOUNCE_SECONDS

    def test_cooldown_is_long(self):
        """Cooldown should be substantially longer than conflict window."""
        assert _COOLDOWN_SECONDS > _CONFLICT_WINDOW_SECONDS * 10
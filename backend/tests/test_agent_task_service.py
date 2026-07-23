"""v1.7 Phase 5 — AgentTaskService 测试."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.config import config
from backend.repository import db
from backend.services import agent_task_service
from backend.services.agent_task_service import (
    create_task,
    list_pending,
    get_task,
    complete_task,
)
from backend.services import agent_task_service as ats


@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_agent_task.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    # 临时重定向任务文件目录到 tmp_path
    tasks_root = tmp_path / "tasks"
    monkeypatch.setattr(agent_task_service, "TASKS_DIR", tasks_root)
    monkeypatch.setattr(agent_task_service, "PENDING_DIR", tasks_root / "pending")
    monkeypatch.setattr(agent_task_service, "PROCESSING_DIR", tasks_root / "processing")
    monkeypatch.setattr(agent_task_service, "DONE_DIR", tasks_root / "done")
    monkeypatch.setattr(agent_task_service, "FAILED_DIR", tasks_root / "failed")
    yield test_db
    db.close_db()


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------
class TestCreateTask:
    def test_creates_db_record(self, temp_db):
        result = create_task("extract", "hotspot", "h-001")
        assert result["task_type"] == "extract"
        assert result["status"] == "pending"
        assert result["target_type"] == "hotspot"
        assert result["target_id"] == "h-001"
        assert result["priority"] == 1
        assert isinstance(result["task_id"], int)

    def test_creates_task_file(self, temp_db):
        result = create_task("extract", "hotspot", "h-002")
        task_file = ats.PENDING_DIR / f"task-{result['task_id']}.md"
        assert task_file.exists()
        content = task_file.read_text(encoding="utf-8")
        assert "task_id:" in content
        assert "extract" in content
        assert "h-002" in content

    def test_priority_stored(self, temp_db):
        result = create_task("compile", "knowledge", "k-001", priority=3)
        assert result["priority"] == 3

    def test_extra_params_merged(self, temp_db):
        result = create_task(
            "publish", "knowledge", "k-002",
            params={"draft_id": 42, "platform": "wechat"},
        )
        task = get_task(result["task_id"])
        assert task["params"]["draft_id"] == 42
        assert task["params"]["platform"] == "wechat"
        assert task["params"]["target_type"] == "knowledge"

    def test_default_params(self, temp_db):
        result = create_task("extract")
        task = get_task(result["task_id"])
        assert task["target_type"] == ""
        assert task["target_id"] == ""
        assert task["priority"] == 1


# ---------------------------------------------------------------------------
# list_pending
# ---------------------------------------------------------------------------
class TestListPending:
    def test_empty_returns_empty_list(self, temp_db):
        assert list_pending() == []

    def test_returns_pending_tasks(self, temp_db):
        create_task("extract", "hotspot", "h-1")
        create_task("compile", "knowledge", "k-1")
        tasks = list_pending()
        assert len(tasks) == 2
        types = {t["task_type"] for t in tasks}
        assert types == {"extract", "compile"}

    def test_limit_respected(self, temp_db):
        for i in range(5):
            create_task("extract", "hotspot", f"h-{i}")
        tasks = list_pending(limit=3)
        assert len(tasks) == 3

    def test_excludes_completed(self, temp_db):
        r1 = create_task("extract", "hotspot", "h-1")
        create_task("compile", "knowledge", "k-1")
        complete_task(r1["task_id"], "done")
        tasks = list_pending()
        assert len(tasks) == 1
        assert tasks[0]["task_type"] == "compile"

    def test_ordered_by_created_at_asc(self, temp_db):
        """先创建的任务排在前面 (FIFO)."""
        import time
        r1 = create_task("extract", "hotspot", "h-first")
        time.sleep(0.05)
        r2 = create_task("extract", "hotspot", "h-second")
        tasks = list_pending()
        assert tasks[0]["task_id"] == r1["task_id"]
        assert tasks[1]["task_id"] == r2["task_id"]


# ---------------------------------------------------------------------------
# get_task
# ---------------------------------------------------------------------------
class TestGetTask:
    def test_returns_task_detail(self, temp_db):
        result = create_task("extract", "hotspot", "h-001", priority=2)
        task = get_task(result["task_id"])
        assert task is not None
        assert task["task_type"] == "extract"
        assert task["target_type"] == "hotspot"
        assert task["target_id"] == "h-001"
        assert task["priority"] == 2

    def test_missing_returns_none(self, temp_db):
        assert get_task(99999) is None


# ---------------------------------------------------------------------------
# complete_task
# ---------------------------------------------------------------------------
class TestCompleteTask:
    def test_complete_done(self, temp_db):
        result = create_task("extract", "hotspot", "h-001")
        completion = complete_task(result["task_id"], "done", {"tags": ["fastapi"]})
        assert completion["success"] is True
        assert completion["status"] == "done"

        task = get_task(result["task_id"])
        assert task["status"] == "done"

    def test_complete_failed(self, temp_db):
        result = create_task("extract", "hotspot", "h-001")
        complete_task(result["task_id"], "failed", error="LLM 不可用")
        task = get_task(result["task_id"])
        assert task["status"] == "failed"
        assert task["error_message"] == "LLM 不可用"

    def test_moves_file_to_done(self, temp_db):
        result = create_task("extract", "hotspot", "h-001")
        task_file = ats.PENDING_DIR / f"task-{result['task_id']}.md"
        assert task_file.exists()
        complete_task(result["task_id"], "done")
        assert not task_file.exists(), "pending 文件应被移走"
        done_file = ats.DONE_DIR / f"task-{result['task_id']}.md"
        assert done_file.exists(), "done 文件应存在"

    def test_moves_file_to_failed(self, temp_db):
        result = create_task("extract", "hotspot", "h-001")
        complete_task(result["task_id"], "failed", error="error")
        failed_file = ats.FAILED_DIR / f"task-{result['task_id']}.md"
        assert failed_file.exists()

    def test_result_stored_in_params(self, temp_db):
        result = create_task("extract", "hotspot", "h-001")
        complete_task(
            result["task_id"], "done",
            result={"tags": ["python", "fastapi"], "count": 2},
        )
        task = get_task(result["task_id"])
        assert task["params"]["result"]["tags"] == ["python", "fastapi"]
        assert task["params"]["result"]["count"] == 2

    def test_complete_nonexistent_raises(self, temp_db):
        """完成不存在的 task 不应静默成功."""
        with pytest.raises(Exception):
            complete_task(99999, "done")


# ---------------------------------------------------------------------------
# 集成: 完整流转
# ---------------------------------------------------------------------------
class TestTaskLifecycle:
    def test_full_lifecycle(self, temp_db):
        """create → list → complete → get 验证完整流转."""
        # 1. 创建
        r = create_task("compile", "knowledge", "k-lifecycle", priority=2)
        assert r["status"] == "pending"

        # 2. 列表可见
        tasks = list_pending()
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == r["task_id"]

        # 3. 完成任务
        complete_task(r["task_id"], "done", result={"compiled": True})

        # 4. 列表不再可见
        tasks = list_pending()
        assert len(tasks) == 0

        # 5. 历史可查
        task = get_task(r["task_id"])
        assert task["status"] == "done"
        assert task["params"]["result"]["compiled"] is True

    def test_multiple_task_types(self, temp_db):
        """多种 task_type 共存."""
        create_task("extract", "hotspot", "h-1")
        create_task("compile", "knowledge", "k-1")
        create_task("publish", "knowledge", "k-2")
        create_task("generate_learning_plan")
        tasks = list_pending()
        types = {t["task_type"] for t in tasks}
        assert types == {"extract", "compile", "publish", "generate_learning_plan"}

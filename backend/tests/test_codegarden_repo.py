"""Phase 2a CodeGarden repo 单测 — CRUD + lifecycle + activities + 筛选。"""
from __future__ import annotations

import sqlite3
from typing import Iterator

import pytest

from backend.exceptions import InternalException
from backend.repository.codegarden_repo import (
    CodegardenProjectRepository,
    VALID_LIFECYCLE_STAGES,
    VALID_PROJECT_TYPES,
    VALID_SOURCE_TYPES,
)


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Iterator:
    """独立临时 DB, 只应用 019_codegarden.sql 的 cg_ 表部分 (跳过 skills ALTER)."""
    db_file = tmp_path / "test_codegarden.db"
    conn = sqlite3.connect(str(db_file))
    # 只执行 cg_ 表的 CREATE TABLE 和 CREATE INDEX, 跳过 ALTER TABLE skills
    with open("backend/repository/migrations/019_codegarden.sql", "r", encoding="utf-8") as f:
        sql_text = f.read()
    cg_sql = "\n".join(
        line for line in sql_text.splitlines()
        if not line.strip().startswith("ALTER TABLE skills")
        and not line.strip().startswith("CREATE INDEX IF NOT EXISTS idx_skills_")
    )
    conn.executescript(cg_sql)
    conn.commit()
    conn.close()

    # Patch get_connection → 我们的 db
    from backend.repository import db as db_mod

    def _get_conn():
        c = sqlite3.connect(str(db_file))
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    monkeypatch.setattr(db_mod, "get_connection", _get_conn)
    # Also patch the symbol imported into codegarden_repo module
    import backend.repository.codegarden_repo as repo_mod
    monkeypatch.setattr(repo_mod, "get_connection", _get_conn)

    yield CodegardenProjectRepository()


def _make_project(repo, **overrides):
    defaults = dict(
        name="test-project",
        type="web_application",
        source_type="vibe",
        lifecycle_stage="ideation",
        tags=["test"],
        tech_stack=["react"],
        domain="frontend",
    )
    defaults.update(overrides)
    return repo.create(**defaults)


def test_create_project_returns_full_record(repo):
    p = _make_project(repo, name="my-app")
    assert p["id"]
    assert p["name"] == "my-app"
    assert p["type"] == "web_application"
    assert p["source_type"] == "vibe"
    assert p["lifecycle_stage"] == "ideation"
    assert p["tags"] == ["test"]
    assert p["tech_stack"] == ["react"]
    assert p["health_score"] == 0
    assert p["commits_behind"] == 0
    assert p["created_at"]
    assert p["last_activity_at"]


def test_create_invalid_type_raises(repo):
    with pytest.raises(InternalException):
        repo.create(name="x", type="invalid", source_type="vibe")


def test_create_invalid_source_type_raises(repo):
    with pytest.raises(InternalException):
        repo.create(name="x", type="cli", source_type="invalid")


def test_create_invalid_lifecycle_raises(repo):
    with pytest.raises(InternalException):
        repo.create(name="x", type="cli", source_type="vibe", lifecycle_stage="bogus")


def test_get_returns_none_for_missing(repo):
    assert repo.get("nonexistent-id") is None


def test_list_filters_by_lifecycle(repo):
    _make_project(repo, name="a", lifecycle_stage="development")
    _make_project(repo, name="b", lifecycle_stage="archived")
    items, total = repo.list(lifecycle_stage="development")
    assert total == 1
    assert items[0]["name"] == "a"


def test_list_excludes_archived_by_default(repo):
    _make_project(repo, name="active", lifecycle_stage="development")
    _make_project(repo, name="archived", lifecycle_stage="archived")
    items, total = repo.list()
    assert total == 1
    assert items[0]["name"] == "active"


def test_list_filter_by_source_item_id(repo):
    _make_project(repo, name="from-news", source_item_id="abc123")
    _make_project(repo, name="manual")
    items, total = repo.list(source_item_id="abc123")
    assert total == 1
    assert items[0]["name"] == "from-news"


def test_list_keyword_search(repo):
    _make_project(repo, name="ai-assistant", description="AI chat")
    _make_project(repo, name="data-pipeline")
    items, total = repo.list(keyword="ai")
    assert total == 1
    assert items[0]["name"] == "ai-assistant"


def test_update_changes_fields(repo):
    p = _make_project(repo)
    updated = repo.update(p["id"], description="new desc", priority=5)
    assert updated["description"] == "new desc"
    assert updated["priority"] == 5


def test_update_rejects_unknown_field(repo):
    p = _make_project(repo)
    with pytest.raises(InternalException):
        repo.update(p["id"], bogus_field="x")


def test_set_lifecycle_writes_activity(repo):
    p = _make_project(repo, lifecycle_stage="ideation")
    updated = repo.set_lifecycle(p["id"], "development", note="开始开发")
    assert updated["lifecycle_stage"] == "development"
    activities = repo.list_activities(p["id"])
    assert len(activities) == 1
    assert activities[0]["activity_type"] == "status_change"
    assert "ideation" in activities[0]["content"]
    assert "development" in activities[0]["content"]


def test_archive_sets_archived_at(repo):
    p = _make_project(repo)
    archived = repo.archive(p["id"])
    assert archived["lifecycle_stage"] == "archived"
    assert archived["archived_at"] is not None


def test_restore_clears_archived_at(repo):
    p = _make_project(repo)
    repo.archive(p["id"])
    restored = repo.restore(p["id"])
    assert restored["lifecycle_stage"] == "maintenance"
    assert restored["archived_at"] is None


def test_delete_removes_project_and_cascades(repo):
    p = _make_project(repo)
    repo.add_activity(project_id=p["id"], activity_type="note", content="hi")
    assert repo.delete(p["id"]) is True
    assert repo.get(p["id"]) is None
    # ON DELETE CASCADE 应级联删除 activities
    assert repo.list_activities(p["id"]) == []


def test_add_activity_updates_last_activity_at(repo):
    p = _make_project(repo)
    original = p["last_activity_at"]
    repo.add_activity(project_id=p["id"], activity_type="note", content="hello")
    updated = repo.get(p["id"])
    assert updated["last_activity_at"] >= original  # type: ignore[operator]


def test_add_stage_auto_increments_order(repo):
    p = _make_project(repo)
    s1 = repo.add_stage(project_id=p["id"], stage_name="原型")
    s2 = repo.add_stage(project_id=p["id"], stage_name="开发")
    assert s1["stage_order"] == 1
    assert s2["stage_order"] == 2


def test_list_stages_returns_in_order(repo):
    p = _make_project(repo)
    repo.add_stage(project_id=p["id"], stage_name="b")
    repo.add_stage(project_id=p["id"], stage_name="a")
    stages = repo.list_stages(p["id"])
    assert [s["stage_name"] for s in stages] == ["b", "a"]

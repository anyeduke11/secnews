"""Phase 2b CodeGarden Orchestration Repository 单测 — dependencies + events."""
from __future__ import annotations

import sqlite3
from typing import Iterator

import pytest

from backend.exceptions import InternalException
from backend.repository.codegarden_orchestration_repo import (
    CodegardenDependencyRepository,
    CodegardenEventRepository,
    VALID_DEP_TYPES,
    VALID_EVENT_TYPES,
)


@pytest.fixture
def dep_repo(tmp_path, monkeypatch) -> Iterator[CodegardenDependencyRepository]:
    db_file = tmp_path / "test_codegarden_orch.db"
    conn = sqlite3.connect(str(db_file))
    with open("backend/repository/migrations/019_codegarden.sql", "r", encoding="utf-8") as f:
        sql_text = f.read()
    cg_sql = "\n".join(
        line for line in sql_text.splitlines()
        if not line.strip().startswith("ALTER TABLE skills")
        and not line.strip().startswith("CREATE INDEX IF NOT EXISTS idx_skills_")
    )
    conn.executescript(cg_sql)
    with open("backend/repository/migrations/021_codegarden_phase2b.sql", "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

    from backend.repository import db as db_mod

    def _get_conn():
        c = sqlite3.connect(str(db_file))
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    monkeypatch.setattr(db_mod, "get_connection", _get_conn)
    import backend.repository.codegarden_orchestration_repo as repo_mod
    monkeypatch.setattr(repo_mod, "get_connection", _get_conn)

    yield CodegardenDependencyRepository()


@pytest.fixture
def event_repo(tmp_path, monkeypatch) -> Iterator[CodegardenEventRepository]:
    """复用 dep_repo 的 DB 设置, 返回 EventRepository."""
    db_file = tmp_path / "test_codegarden_orch.db"
    conn = sqlite3.connect(str(db_file))
    with open("backend/repository/migrations/019_codegarden.sql", "r", encoding="utf-8") as f:
        sql_text = f.read()
    cg_sql = "\n".join(
        line for line in sql_text.splitlines()
        if not line.strip().startswith("ALTER TABLE skills")
        and not line.strip().startswith("CREATE INDEX IF NOT EXISTS idx_skills_")
    )
    conn.executescript(cg_sql)
    with open("backend/repository/migrations/021_codegarden_phase2b.sql", "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

    from backend.repository import db as db_mod

    def _get_conn():
        c = sqlite3.connect(str(db_file))
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    monkeypatch.setattr(db_mod, "get_connection", _get_conn)
    import backend.repository.codegarden_orchestration_repo as repo_mod
    monkeypatch.setattr(repo_mod, "get_connection", _get_conn)

    yield CodegardenEventRepository()


# ===========================================================================
# Dependencies (8 测试)
# ===========================================================================
def test_create_dependency_returns_full_record(dep_repo):
    d = dep_repo.create(
        source_type="project", source_id="proj-1",
        target_type="project", target_id="proj-2",
        dep_type="code",
    )
    assert d["id"]
    assert d["source_type"] == "project"
    assert d["source_id"] == "proj-1"
    assert d["target_type"] == "project"
    assert d["target_id"] == "proj-2"
    assert d["dep_type"] == "code"
    assert d["metadata"] == {}
    assert d["created_at"]


def test_create_dependency_invalid_dep_type_rejected(dep_repo):
    with pytest.raises(InternalException):
        dep_repo.create(
            source_type="project", source_id="a",
            target_type="project", target_id="b",
            dep_type="invalid",
        )


def test_create_dependency_invalid_source_type_rejected(dep_repo):
    with pytest.raises(InternalException):
        dep_repo.create(
            source_type="invalid", source_id="a",
            target_type="project", target_id="b",
            dep_type="code",
        )


def test_create_dependency_unique_constraint(dep_repo):
    dep_repo.create(
        source_type="project", source_id="a",
        target_type="project", target_id="b",
        dep_type="code",
    )
    # 重复创建应抛 UNIQUE 异常
    with pytest.raises(InternalException):
        dep_repo.create(
            source_type="project", source_id="a",
            target_type="project", target_id="b",
            dep_type="code",
        )
    # 但同一 source-target 不同 dep_type 允许
    d2 = dep_repo.create(
        source_type="project", source_id="a",
        target_type="project", target_id="b",
        dep_type="data",
    )
    assert d2["dep_type"] == "data"


def test_list_filter_by_source(dep_repo):
    dep_repo.create(source_type="project", source_id="a", target_type="project", target_id="b", dep_type="code")
    dep_repo.create(source_type="project", source_id="c", target_type="project", target_id="d", dep_type="code")
    deps, total = dep_repo.list(source_id="a")
    assert total == 1
    assert deps[0]["source_id"] == "a"


def test_delete_dependency(dep_repo):
    d = dep_repo.create(source_type="project", source_id="a", target_type="project", target_id="b", dep_type="code")
    assert dep_repo.delete(d["id"]) is True
    assert dep_repo.get(d["id"]) is None


def test_impact_analysis_direct(dep_repo):
    # a → b (a 依赖 b)
    dep_repo.create(source_type="project", source_id="a", target_type="project", target_id="b", dep_type="code")
    # c → b (c 也依赖 b)
    dep_repo.create(source_type="project", source_id="c", target_type="project", target_id="b", dep_type="code")
    # 修改 b 影响哪些 source? → a 和 c
    impacts = dep_repo.impact_analysis(target_type="project", target_id="b")
    impact_sources = {d["source_id"] for d in impacts}
    assert impact_sources == {"a", "c"}


def test_impact_analysis_transitive(dep_repo):
    # a → b → c (a 依赖 b, b 依赖 c)
    dep_repo.create(source_type="project", source_id="a", target_type="project", target_id="b", dep_type="code")
    dep_repo.create(source_type="project", source_id="b", target_type="project", target_id="c", dep_type="code")
    # 修改 c 影响哪些 source? → b (直接) + a (间接, 经 b)
    impacts = dep_repo.impact_analysis(target_type="project", target_id="c")
    impact_sources = {d["source_id"] for d in impacts}
    assert impact_sources == {"a", "b"}


# ===========================================================================
# Events (6 测试)
# ===========================================================================
def test_create_event_returns_full_record(event_repo):
    e = event_repo.create(
        event_type="port_conflict",
        source_type="service",
        source_id="svc-1",
        payload={"port": 8080},
    )
    assert e["id"]
    assert e["event_type"] == "port_conflict"
    assert e["source_type"] == "service"
    assert e["source_id"] == "svc-1"
    assert e["payload"] == {"port": 8080}
    assert e["status"] == "pending"  # default
    assert e["created_at"]
    assert e["processed_at"] is None
    assert e["error_message"] is None


def test_create_event_invalid_type_rejected(event_repo):
    with pytest.raises(InternalException):
        event_repo.create(
            event_type="invalid", source_type="service", source_id="x",
        )


def test_create_event_invalid_source_rejected(event_repo):
    with pytest.raises(InternalException):
        event_repo.create(
            event_type="port_conflict", source_type="invalid", source_id="x",
        )


def test_list_filter_by_status(event_repo):
    event_repo.create(event_type="port_conflict", source_type="service", source_id="a")
    event_repo.create(event_type="code_push", source_type="project", source_id="b")
    events, total = event_repo.list(status="pending")
    assert total == 2


def test_list_pending_returns_oldest_first(event_repo):
    e1 = event_repo.create(event_type="port_conflict", source_type="service", source_id="a")
    e2 = event_repo.create(event_type="code_push", source_type="project", source_id="b")
    pending = event_repo.list_pending()
    assert len(pending) == 2
    # 旧的先 (创建时间升序)
    assert pending[0]["id"] == e1["id"]
    assert pending[1]["id"] == e2["id"]


def test_mark_processed_success_and_failure(event_repo):
    e1 = event_repo.create(event_type="port_conflict", source_type="service", source_id="a")
    e2 = event_repo.create(event_type="code_push", source_type="project", source_id="b")

    # 成功处理
    r1 = event_repo.mark_processed(e1["id"], success=True)
    assert r1["status"] == "processed"
    assert r1["processed_at"]
    assert r1["error_message"] is None

    # 处理失败
    r2 = event_repo.mark_processed(e2["id"], success=False, error_message="handler crashed")
    assert r2["status"] == "failed"
    assert r2["error_message"] == "handler crashed"

    # list_pending 不再返回已处理的
    pending = event_repo.list_pending()
    assert len(pending) == 0

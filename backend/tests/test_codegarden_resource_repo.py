"""Phase 2b CodeGarden Resource Repository 单测 — CRUD + find_free_port + release_port."""
from __future__ import annotations

import sqlite3
from typing import Iterator

import pytest

from backend.exceptions import InternalException
from backend.repository.codegarden_resource_repo import (
    CodegardenResourceRepository,
    PROTECTED_PORTS,
    PORT_RANGE_START,
    PORT_RANGE_END,
)


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Iterator[CodegardenResourceRepository]:
    """独立临时 DB, 加载 019 (cg_projects) + 021 (cg_resources)."""
    db_file = tmp_path / "test_codegarden_resources.db"
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
    import backend.repository.codegarden_resource_repo as repo_mod
    monkeypatch.setattr(repo_mod, "get_connection", _get_conn)

    yield CodegardenResourceRepository()


# ---------------------------------------------------------------------------
# CRUD (5 测试)
# ---------------------------------------------------------------------------
def test_create_resource_port(repo):
    r = repo.create(type="port", value="8080", status="free")
    assert r["id"]
    assert r["type"] == "port"
    assert r["value"] == "8080"
    assert r["status"] == "free"
    assert r["metadata"] == {}
    assert r["created_at"]


def test_create_resource_invalid_type_rejected(repo):
    with pytest.raises(InternalException):
        repo.create(type="invalid", value="x")


def test_get_by_value(repo):
    repo.create(type="port", value="8080")
    r = repo.get_by_value("port", "8080")
    assert r is not None
    assert r["value"] == "8080"


def test_list_filter_by_type(repo):
    repo.create(type="port", value="8080")
    repo.create(type="domain", value="test.local")
    ports, total = repo.list(type="port")
    assert total == 1
    assert ports[0]["type"] == "port"


def test_update_and_delete(repo):
    r = repo.create(type="port", value="8080", status="free")
    updated = repo.update(r["id"], status="allocated")
    assert updated["status"] == "allocated"
    assert repo.delete(r["id"]) is True
    assert repo.get(r["id"]) is None


# ---------------------------------------------------------------------------
# find_free_port (3 测试)
# ---------------------------------------------------------------------------
def test_find_free_port_returns_smallest_available(repo):
    port = repo.find_free_port()
    assert port == PORT_RANGE_START  # 8000, 无已分配


def test_find_free_port_skips_allocated(repo):
    repo.allocate_port(8000)
    repo.allocate_port(8001)
    port = repo.find_free_port()
    assert port == 8002


def test_find_free_port_skips_protected_and_excluded(repo):
    # 8898 受保护, 即使表内无记录也不返回
    repo.allocate_port(8000)
    port = repo.find_free_port(exclude_ports={8001})
    assert port == 8002  # 8000 allocated, 8001 excluded, 8002 free
    assert 8898 not in {repo.find_free_port() for _ in range(20)}  # 8898 不会被返回


# ---------------------------------------------------------------------------
# allocate_port + release_port (2 测试)
# ---------------------------------------------------------------------------
def test_allocate_port_creates_new_record(repo):
    # 不传 owner_project_id 避免外键约束 (proj-1 不存在)
    r = repo.allocate_port(8080)
    assert r["status"] == "allocated"
    assert r["owner_project_id"] is None
    assert r["value"] == "8080"


def test_release_port_clears_owner(repo):
    repo.allocate_port(8080)
    r = repo.release_port(8080)
    assert r["status"] == "free"
    assert r["owner_project_id"] is None

"""Phase 2b CodeGarden Service Repository 单测 — CRUD + 筛选 + upsert_from_scan."""
from __future__ import annotations

import sqlite3
from typing import Iterator

import pytest

from backend.exceptions import InternalException
from backend.repository.codegarden_service_repo import (
    CodegardenServiceRepository,
    VALID_SERVICE_TYPES,
    VALID_RUNTIMES,
    VALID_SERVICE_STATUSES,
)


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Iterator[CodegardenServiceRepository]:
    """独立临时 DB, 加载 019 (cg_projects) + 021 (cg_services)."""
    db_file = tmp_path / "test_codegarden_services.db"
    conn = sqlite3.connect(str(db_file))
    # 019: 跳过 skills ALTER
    with open("backend/repository/migrations/019_codegarden.sql", "r", encoding="utf-8") as f:
        sql_text = f.read()
    cg_sql = "\n".join(
        line for line in sql_text.splitlines()
        if not line.strip().startswith("ALTER TABLE skills")
        and not line.strip().startswith("CREATE INDEX IF NOT EXISTS idx_skills_")
    )
    conn.executescript(cg_sql)
    # 021: cg_services 等
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
    import backend.repository.codegarden_service_repo as repo_mod
    monkeypatch.setattr(repo_mod, "get_connection", _get_conn)

    yield CodegardenServiceRepository()


def _make_service(repo, **overrides):
    defaults = dict(
        name="test-api",
        type="http",
        runtime="docker",
        status="running",
        endpoint_host="127.0.0.1",
        endpoint_port=3000,
        namespace="test.ns",
    )
    defaults.update(overrides)
    return repo.create(**defaults)


# ---------------------------------------------------------------------------
# CRUD (7 测试)
# ---------------------------------------------------------------------------
def test_create_service_returns_full_record(repo):
    s = _make_service(repo, name="my-svc")
    assert s["id"]
    assert s["name"] == "my-svc"
    assert s["type"] == "http"
    assert s["runtime"] == "docker"
    assert s["status"] == "running"
    assert s["endpoint_port"] == 3000
    assert s["endpoint_host"] == "127.0.0.1"
    assert s["namespace"] == "test.ns"
    assert s["dependencies"] == []
    assert s["env_vars"] == {}
    assert s["created_at"]
    assert s["last_checked_at"]


def test_create_service_invalid_type_rejected(repo):
    with pytest.raises(InternalException):
        repo.create(name="x", type="invalid", runtime="docker")


def test_create_service_invalid_runtime_rejected(repo):
    with pytest.raises(InternalException):
        repo.create(name="x", type="http", runtime="kubernetes")


def test_create_service_invalid_status_rejected(repo):
    with pytest.raises(InternalException):
        repo.create(name="x", type="http", runtime="docker", status="zombie")


def test_get_nonexistent_returns_none(repo):
    assert repo.get("nonexistent-id") is None


def test_update_service_fields(repo):
    s = _make_service(repo)
    updated = repo.update(s["id"], status="stopped", endpoint_port=4000)
    assert updated["status"] == "stopped"
    assert updated["endpoint_port"] == 4000


def test_delete_service(repo):
    s = _make_service(repo)
    assert repo.delete(s["id"]) is True
    assert repo.get(s["id"]) is None
    # 二次删除返回 False
    assert repo.delete(s["id"]) is False


# ---------------------------------------------------------------------------
# list 筛选 (3 测试)
# ---------------------------------------------------------------------------
def test_list_filter_by_status(repo):
    _make_service(repo, name="a", status="running")
    _make_service(repo, name="b", status="stopped")
    services, total = repo.list(status="running")
    assert total == 1
    assert services[0]["name"] == "a"


def test_list_filter_by_namespace(repo):
    _make_service(repo, name="a", namespace="ns1")
    _make_service(repo, name="b", namespace="ns2")
    services, total = repo.list(namespace="ns1")
    assert total == 1
    assert services[0]["namespace"] == "ns1"


def test_list_filter_by_keyword(repo):
    _make_service(repo, name="api-server")
    _make_service(repo, name="web-ui")
    services, total = repo.list(keyword="api")
    assert total == 1
    assert services[0]["name"] == "api-server"


# ---------------------------------------------------------------------------
# upsert_from_scan (2 测试)
# ---------------------------------------------------------------------------
def test_upsert_from_scan_creates_new_service(repo):
    svc, created = repo.upsert_from_scan(
        name="scanned-svc",
        type="http",
        runtime="docker",
        status="running",
        endpoint_port=8080,
    )
    assert created is True
    assert svc["name"] == "scanned-svc"
    assert svc["endpoint_port"] == 8080
    assert svc["status"] == "running"


def test_upsert_from_scan_updates_existing(repo):
    # 第一次扫描
    svc1, created1 = repo.upsert_from_scan(
        name="scanned-svc", type="http", runtime="docker",
        status="running", endpoint_port=8080,
    )
    assert created1 is True
    # 第二次扫描同一服务, 状态变化
    svc2, created2 = repo.upsert_from_scan(
        name="scanned-svc", type="http", runtime="docker",
        status="stopped", endpoint_port=8080,
    )
    assert created2 is False
    assert svc2["id"] == svc1["id"]
    assert svc2["status"] == "stopped"

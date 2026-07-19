"""Phase 2a CodeGarden API 单测 — 16 个端点全覆盖.

策略
----
- 独立临时 DB (tmp_path + monkeypatch): 应用 018_knowledge.sql + 019_codegarden.sql
- 项目 CRUD / lifecycle / activities: 直接测, 无需 mock
- github_import / upstream: mock codegarden_github_service 函数
- from_knowledge: 准备 knowledge_item 数据, 真实跑转化流程
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Iterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture: 独立临时 DB + TestClient
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """独立临时 DB 跑 FastAPI TestClient.

    应用迁移:
    - 018_knowledge.sql (knowledge_items / knowledge_tasks / knowledge_concepts)
    - 019_codegarden.sql (cg_projects / cg_project_stages / cg_project_links /
      cg_project_activities + skills ALTER)
    """
    db_file = tmp_path / "test_codegarden_api.db"

    conn = sqlite3.connect(str(db_file))
    # 018: knowledge_items + knowledge_tasks (test_create_from_knowledge / test_trigger_sync 需要)
    with open("backend/repository/migrations/018_knowledge.sql", "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    # 019: cg_projects 等 (跳过 ALTER TABLE skills, 测试 DB 无 skills 表)
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
    from backend import repository as repo_pkg
    from backend.repository import db as db_mod

    def _get_conn():
        c = sqlite3.connect(str(db_file), check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    monkeypatch.setattr(db_mod, "get_connection", _get_conn)
    for name in list(repo_pkg.__dict__.keys()):
        m = getattr(repo_pkg, name)
        if hasattr(m, "get_connection"):
            try:
                monkeypatch.setattr(m, "get_connection", _get_conn)
            except (AttributeError, TypeError):
                pass

    # 也 patch 服务层 import 的 get_connection
    import backend.services.codegarden_knowledge_bridge as bridge_mod
    monkeypatch.setattr(bridge_mod, "get_connection", _get_conn)

    # 用全新 FastAPI app (不复用 backend.main.app, 避免 lifespan 启动 scheduler)
    from backend.api.codegarden import router
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)


def _seed_knowledge_item(source_url: str = "https://github.com/foo/bar") -> str:
    """插入一条 type=github 的 knowledge_item, 返回其 id。

    注意: 必须通过 backend.repository.db.get_connection (而非 from ... import get_connection)
    以使用 monkeypatched 的版本, 否则数据写到生产 DB 而非 tmp_path DB。
    SQLite 默认 isolation_level='' 非 autocommit, 需显式 commit 才能让 API 端读到。
    """
    from backend.repository import db as db_mod
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = db_mod.get_connection()
    conn.execute(
        """
        INSERT INTO knowledge_items
        (id, title, source, source_url, domain, topic, type, difficulty,
         tags, concepts, mastery, compiled, ingested_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
        """,
        (item_id, "foo/bar: test repo", "github-trending",
         source_url, "github", None, "github", None,
         "[]", "[]", now, now),
    )
    conn.commit()
    return item_id


# ---------------------------------------------------------------------------
# 项目 CRUD
# ---------------------------------------------------------------------------
def test_create_project_returns_201(client):
    r = client.post("/api/codegarden/projects", json={
        "name": "test-api",
        "type": "web_application",
        "source_type": "vibe",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["id"]
    assert data["name"] == "test-api"
    assert data["lifecycle_stage"] == "ideation"


def test_create_project_invalid_type_returns_400(client):
    r = client.post("/api/codegarden/projects", json={
        "name": "x", "type": "bogus", "source_type": "vibe",
    })
    assert r.status_code == 400


def test_list_projects_returns_created(client):
    client.post("/api/codegarden/projects", json={
        "name": "list-target", "type": "cli", "source_type": "vibe",
    })
    r = client.get("/api/codegarden/projects")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any(p["name"] == "list-target" for p in data["items"])


def test_get_project_404(client):
    r = client.get("/api/codegarden/projects/nonexistent-id")
    assert r.status_code == 404


def test_patch_project_updates_fields(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "patch-me", "type": "cli", "source_type": "vibe",
    }).json()
    r = client.patch(f"/api/codegarden/projects/{create['id']}", json={
        "description": "updated",
        "priority": 5,
    })
    assert r.status_code == 200
    assert r.json()["description"] == "updated"
    assert r.json()["priority"] == 5


def test_change_lifecycle_writes_activity(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "lc", "type": "cli", "source_type": "vibe",
    }).json()
    r = client.post(f"/api/codegarden/projects/{create['id']}/lifecycle",
                    json={"to": "prototype"})
    assert r.status_code == 200
    assert r.json()["lifecycle_stage"] == "prototype"
    # 验证活动日志
    acts = client.get(f"/api/codegarden/projects/{create['id']}/activities").json()
    assert any(a["activity_type"] == "status_change" for a in acts["activities"])


def test_change_lifecycle_rejects_invalid_transition(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "lc2", "type": "cli", "source_type": "vibe",
        "lifecycle_stage": "ideation",
    }).json()
    # ideation → running 非法 (跳过 prototype/development/testing)
    r = client.post(f"/api/codegarden/projects/{create['id']}/lifecycle",
                    json={"to": "running"})
    assert r.status_code == 400


def test_archive_and_restore(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "arc", "type": "cli", "source_type": "vibe",
        "lifecycle_stage": "development",
    }).json()
    r = client.post(f"/api/codegarden/projects/{create['id']}/archive")
    assert r.status_code == 200
    assert r.json()["lifecycle_stage"] == "archived"
    assert r.json()["archived_at"] is not None

    r = client.post(f"/api/codegarden/projects/{create['id']}/restore")
    assert r.status_code == 200
    assert r.json()["lifecycle_stage"] == "maintenance"
    assert r.json()["archived_at"] is None


def test_delete_project(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "del", "type": "cli", "source_type": "vibe",
    }).json()
    r = client.delete(f"/api/codegarden/projects/{create['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    # 二次 get 应 404
    assert client.get(f"/api/codegarden/projects/{create['id']}").status_code == 404


def test_get_timeline_returns_stages(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "tl", "type": "cli", "source_type": "vibe",
    }).json()
    r = client.get(f"/api/codegarden/projects/{create['id']}/timeline")
    assert r.status_code == 200
    assert "stages" in r.json()


# ---------------------------------------------------------------------------
# GitHub 导入 (mock)
# ---------------------------------------------------------------------------
def test_github_import_returns_424_when_no_token(client):
    from backend.services.codegarden_github_service import GithubTokenMissingException
    with patch("backend.services.codegarden_github_service.fetch_repo_metadata",
               side_effect=GithubTokenMissingException("no token")):
        r = client.post("/api/codegarden/github/import", json={
            "repo_url": "https://github.com/foo/bar",
        })
    assert r.status_code == 424
    assert "github_token" in r.json()["detail"]["missing"]


def test_github_import_creates_project(client):
    from backend.services.codegarden_github_service import RepoMetadata
    fake_meta = RepoMetadata(
        owner="foo", repo="bar", default_branch="main",
        description="test repo", upstream_url=None,
        upstream_default_branch=None, stars=100, language="Python",
        homepage=None,
    )
    with patch("backend.services.codegarden_github_service.fetch_repo_metadata",
               return_value=fake_meta):
        r = client.post("/api/codegarden/github/import", json={
            "repo_url": "https://github.com/foo/bar",
            "auto_sync": False,
        })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["source_type"] == "imported"  # 无 upstream_url
    assert data["repo_url"] == "https://github.com/foo/bar"
    assert data["upstream_default_branch"] == "main"
    assert "Python" in data["tech_stack"]


def test_github_import_fork_with_upstream(client):
    from backend.services.codegarden_github_service import RepoMetadata
    fake_meta = RepoMetadata(
        owner="me", repo="bar-fork", default_branch="main",
        description="my fork", upstream_url="https://github.com/foo/bar.git",
        upstream_default_branch="main", stars=0, language="Python",
        homepage=None,
    )
    with patch("backend.services.codegarden_github_service.fetch_repo_metadata",
               return_value=fake_meta):
        r = client.post("/api/codegarden/github/import", json={
            "repo_url": "https://github.com/me/bar-fork",
            "auto_sync": False,
        })
    assert r.status_code == 201
    data = r.json()
    assert data["source_type"] == "fork"
    assert data["upstream_url"] == "https://github.com/foo/bar.git"


# ---------------------------------------------------------------------------
# from-knowledge 转化 (需要 knowledge_item fixture)
# ---------------------------------------------------------------------------
def test_list_candidates_returns_github_items(client):
    item_id = _seed_knowledge_item()
    r = client.get("/api/codegarden/candidates")
    assert r.status_code == 200
    assert any(it["id"] == item_id for it in r.json()["items"])


def test_create_from_knowledge(client):
    item_id = _seed_knowledge_item()
    r = client.post("/api/codegarden/from-knowledge", json={
        "item_id": item_id,
        "source_type": "fork",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["source_item_id"] == item_id
    assert data["source_type"] == "fork"
    assert data["upstream_url"] == "https://github.com/foo/bar"

    # 候选列表中应不再出现该 item
    cands = client.get("/api/codegarden/candidates").json()
    assert not any(it["id"] == item_id for it in cands["items"])

    # 可通过 source_item_id 反查
    by_src = client.get(f"/api/codegarden/projects?source_item_id={item_id}").json()
    assert by_src["total"] == 1


def test_create_from_knowledge_is_idempotent(client):
    """重复转化同一 knowledge_item 应幂等返回 200 (而非 400)。"""
    item_id = _seed_knowledge_item()
    first = client.post("/api/codegarden/from-knowledge", json={
        "item_id": item_id,
        "source_type": "fork",
    })
    assert first.status_code == 201
    first_id = first.json()["id"]

    second = client.post("/api/codegarden/from-knowledge", json={
        "item_id": item_id,
        "source_type": "fork",
    })
    assert second.status_code == 200  # 幂等: 重复 200, 不创建新 project
    assert second.json()["id"] == first_id  # 返回既有 project


# ---------------------------------------------------------------------------
# 触发同步
# ---------------------------------------------------------------------------
def test_trigger_sync_creates_task(client):
    create = client.post("/api/codegarden/projects", json={
        "name": "sync-me", "type": "cli", "source_type": "fork",
        "repo_url": "https://github.com/foo/bar",
    }).json()
    r = client.post(f"/api/codegarden/projects/{create['id']}/sync")
    assert r.status_code == 200
    assert "task_id" in r.json()

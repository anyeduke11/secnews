"""Phase 41 Skills API 测试。

覆盖:
- 列表 (空 + 多 + 过滤)
- 新增 + 必填校验
- PATCH 部分更新
- DELETE 软链
- 异常路径: 不存在、source 非法
"""
from __future__ import annotations

import os
import sqlite3
from typing import Iterator

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator:
    """独立临时 DB 跑 FastAPI TestClient, 应用 skills migration。"""
    db_file = tmp_path / "test_skills.db"

    # 初始化 schema (012_skills.sql)
    conn = sqlite3.connect(str(db_file))
    with open("backend/repository/migrations/012_skills.sql", "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

    # Patch get_connection → 我们的 db
    from backend import repository as repo_pkg
    from backend.repository import db as db_mod

    def _get_conn():
        c = sqlite3.connect(str(db_file), check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(db_mod, "get_connection", _get_conn)
    for name in list(repo_pkg.__dict__.keys()):
        m = getattr(repo_pkg, name)
        if hasattr(m, "get_connection"):
            try:
                monkeypatch.setattr(m, "get_connection", _get_conn)
            except (AttributeError, TypeError):
                pass

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.skills import router

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)


def test_list_empty(client):
    r = client.get("/api/skills")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_add_then_list(client):
    payload = {
        "name": "aihot",
        "url": "https://github.com/xxx/aihot",
        "install_command": "npx -y aihot@latest",
        "description": "AI 中文资讯",
        "source": "npx",
        "tags": ["ai", "news"],
    }
    r = client.post("/api/skills", json=payload)
    assert r.status_code == 201, r.text
    item = r.json()["item"]
    assert item["name"] == "aihot"
    assert item["source"] == "npx"
    assert item["tags"] == ["ai", "news"]

    r2 = client.get("/api/skills")
    assert r2.status_code == 200
    data = r2.json()
    assert data["total"] == 1
    assert data["items"][0]["install_command"] == "npx -y aihot@latest"


def test_add_required_fields(client):
    r = client.post("/api/skills", json={"name": "x"})
    assert r.status_code == 422 or r.status_code == 500
    # FastAPI validation returns 422 for missing required fields


def test_add_invalid_source(client):
    r = client.post(
        "/api/skills",
        json={
            "name": "x",
            "url": "https://x.com",
            "install_command": "echo x",
            "source": "invalid-source",
        },
    )
    assert r.status_code in (400, 422, 500)


def test_filter_by_source(client):
    client.post(
        "/api/skills",
        json={"name": "n1", "url": "u", "install_command": "c", "source": "npx"},
    )
    client.post(
        "/api/skills",
        json={"name": "u1", "url": "u", "install_command": "c", "source": "uvx"},
    )
    r = client.get("/api/skills?source=npx")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["source"] == "npx"


def test_filter_by_keyword(client):
    client.post(
        "/api/skills",
        json={"name": "aihot", "url": "u", "install_command": "c", "description": "中文"},
    )
    client.post(
        "/api/skills",
        json={"name": "foo", "url": "u", "install_command": "c", "description": "english"},
    )
    r = client.get("/api/skills?keyword=aihot")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "aihot"


def test_patch_partial(client):
    r = client.post(
        "/api/skills",
        json={"name": "a", "url": "u", "install_command": "c"},
    )
    sid = r.json()["item"]["id"]
    p = client.patch(f"/api/skills/{sid}", json={"description": "new desc"})
    assert p.status_code == 200
    assert p.json()["item"]["description"] == "new desc"
    assert p.json()["item"]["name"] == "a"  # 未动


def test_patch_404(client):
    r = client.patch("/api/skills/99999", json={"name": "x"})
    assert r.status_code in (404, 500)


def test_delete(client):
    r = client.post(
        "/api/skills",
        json={"name": "delme", "url": "u", "install_command": "c"},
    )
    sid = r.json()["item"]["id"]
    d = client.delete(f"/api/skills/{sid}")
    assert d.status_code == 204
    lst = client.get("/api/skills")
    assert lst.json()["total"] == 0


def test_count_by_source(client):
    for src in ["npx", "npx", "uvx", "git"]:
        client.post(
            "/api/skills",
            json={"name": f"a-{src}-{id(src)}", "url": "u", "install_command": "c", "source": src},
        )
    r = client.get("/api/skills/count_by_source")
    assert r.status_code == 200
    counts = r.json()["counts"]
    assert counts.get("npx", 0) >= 2
    assert counts.get("uvx", 0) >= 1
    assert counts.get("git", 0) >= 1
    assert counts.get("all", 0) >= 4

"""Phase 2a Task H3 — e2e 测试: 资讯→项目转化全流程.

验证完整路径:
1. knowledge_items.type=github → /api/codegarden/candidates 可见
2. POST /api/codegarden/from-knowledge → 201 + cg_projects 创建
3. cg_projects.source_item_id 反向溯源 = knowledge_item.id
4. /api/codegarden/candidates 转化后该 item 不可见 (C3 SQL 过滤)
5. GET /api/codegarden/projects?source_item_id=... 反查 project
6. 重复转化 → 200 + 同一 project (幂等)
7. type != github 的 item 转化 → 400

fixture 模式参考 test_codegarden_api.py (避免触发 backend.main.app 的 lifespan).
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture: 独立 DB + TestClient (复用 test_codegarden_api.py 的成熟模式)
# ---------------------------------------------------------------------------
@pytest.fixture()
def e2e_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """独立临时 DB + 仅挂 codegarden router (避免启动 scheduler)."""
    db_file = tmp_path / "test_codegarden_e2e.db"

    conn = sqlite3.connect(str(db_file))
    # 018: knowledge_items + knowledge_tasks (from-knowledge 需要)
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

    # Patch get_connection 指向临时 DB
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

    # bridge 层 import 的 get_connection 也要 patch
    import backend.services.codegarden_knowledge_bridge as bridge_mod
    monkeypatch.setattr(bridge_mod, "get_connection", _get_conn)

    # 仅挂 codegarden router (避免 backend.main.app 的 lifespan 启动 scheduler)
    from backend.api.codegarden import router
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)


def _seed_knowledge_item(item_type: str = "github", source_url: str = "https://github.com/anthropics/anthropic-sdk-python") -> str:
    """插入一条 knowledge_item, 返回其 id."""
    from backend.repository import db as db_mod
    item_id = f"{item_type}-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = db_mod.get_connection()
    conn.execute(
        """
        INSERT INTO knowledge_items
        (id, title, source, source_url, domain, topic, type, difficulty,
         tags, concepts, mastery, compiled, ingested_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
        """,
        (item_id, "anthropics/anthropic-sdk-python", "github-trending",
         source_url, "ai", None, item_type, None,
         "[]", "[]", now, now),
    )
    conn.commit()
    return item_id


# ---------------------------------------------------------------------------
# e2e 测试 1: 完整转化路径
# ---------------------------------------------------------------------------
def test_e2e_knowledge_to_codegarden_flow(e2e_client: TestClient):
    """验证完整转化路径: 资讯 → 项目 → 反向溯源."""
    # Step 1: seed knowledge item (type=github)
    item_id = _seed_knowledge_item()

    # Step 2: candidates 列表中可见该 item (转化前)
    r = e2e_client.get("/api/codegarden/candidates")
    assert r.status_code == 200
    candidate_ids = [c["id"] for c in r.json()["items"]]
    assert item_id in candidate_ids, "转化前 item 应在 candidates 列表中"

    # Step 3: 调用 from-knowledge 转化
    r = e2e_client.post(
        "/api/codegarden/from-knowledge",
        json={"item_id": item_id, "source_type": "reference"},
    )
    assert r.status_code == 201, f"首次转化应返回 201: {r.status_code} {r.text}"
    project = r.json()

    # Step 4: 验证 cg_projects 字段 (反向溯源)
    assert project["source_item_id"] == item_id, "source_item_id 必须等于 knowledge_item.id"
    assert project["source_type"] == "reference"
    assert project["repo_url"] == "https://github.com/anthropics/anthropic-sdk-python"
    assert project["name"], "name 不能为空"

    # Step 5: candidates 列表中该 item 已不再出现 (C3 SQL 过滤)
    r = e2e_client.get("/api/codegarden/candidates")
    candidate_ids_after = [c["id"] for c in r.json()["items"]]
    assert item_id not in candidate_ids_after, "转化后 item 应从 candidates 移除"

    # Step 6: 通过 source_item_id 反查 project
    r = e2e_client.get(f"/api/codegarden/projects?source_item_id={item_id}")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1, "通过 source_item_id 反查应只返回 1 条"
    assert items[0]["id"] == project["id"]


# ---------------------------------------------------------------------------
# e2e 测试 2: 重复转化幂等
# ---------------------------------------------------------------------------
def test_e2e_duplicate_conversion_returns_existing(e2e_client: TestClient):
    """同一 knowledge_item 重复调用 from-knowledge 应幂等返回同一 project."""
    item_id = _seed_knowledge_item()

    # 第一次转化 → 201
    r1 = e2e_client.post(
        "/api/codegarden/from-knowledge",
        json={"item_id": item_id, "source_type": "reference"},
    )
    assert r1.status_code == 201
    project1 = r1.json()

    # 第二次转化 → 200 (幂等, 不重复创建)
    r2 = e2e_client.post(
        "/api/codegarden/from-knowledge",
        json={"item_id": item_id, "source_type": "reference"},
    )
    assert r2.status_code == 200, f"重复转化应返回 200: {r2.status_code} {r2.text}"
    project2 = r2.json()

    assert project1["id"] == project2["id"], "重复转化必须返回同一 project"


# ---------------------------------------------------------------------------
# e2e 测试 3: 非 github item 拒绝转化
# ---------------------------------------------------------------------------
def test_e2e_non_github_item_rejected(e2e_client: TestClient):
    """type != github 的 knowledge_item 不应能转化."""
    item_id = _seed_knowledge_item(
        item_type="ai",
        source_url="https://example.com/news",
    )

    r = e2e_client.post(
        "/api/codegarden/from-knowledge",
        json={"item_id": item_id, "source_type": "reference"},
    )
    assert r.status_code == 400, f"type=ai 的 item 不应能转化: {r.status_code}"
    # API 返回 {"detail": {"message": "..."}} — detail 是 dict
    detail = r.json().get("detail", {})
    msg = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    assert "github" in msg.lower(), f"错误消息应提及 github: {msg}"

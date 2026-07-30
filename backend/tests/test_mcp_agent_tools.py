"""Phase 8 — 4 个新 MCP tool 测试.

4 tool × 2 用例（正常 + 异常）= 8 个单测:

- score_item: 写入 ai_scores 表
- enrich_concept: 写入 concepts/{name}.md
- link_items: 写入 knowledge_links 表
- trigger_codegarden_drift: 评估 project tech_stack（stub）
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import register_routers
from backend.api import mcp_agent_tools
from backend.config import config
from backend.repository import db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    test_db = tmp_path / "test_mcp_agent_tools.db"
    monkeypatch.setattr(config, "db_path", test_db)
    db.close_db()
    db.init_db()
    yield test_db
    db.close_db()


@pytest.fixture
def client(temp_db):
    app = FastAPI()
    register_routers(app)
    return TestClient(app)


@pytest.fixture
def tmp_concept_dir(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """将 CONCEPT_DIR 重定向到临时目录，避免污染真实 knowledge/ 目录。"""
    concept_dir = tmp_path / "concepts"
    concept_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mcp_agent_tools, "CONCEPT_DIR", str(concept_dir))
    yield concept_dir


def _insert_hotspot(hid: str, title: str = "测试"):
    """向 hotspots 表插入一条测试记录。"""
    now = datetime.now(timezone.utc).isoformat()
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO hotspots "
        "(id, title, summary, source, url, category, published_at, score, "
        "fetched_at, is_fallback, quality_score, quality_flags, url_check_status, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (hid, title, "summary", "test", f"https://example.com/{hid}",
         "ai", now, 50.0, now, 0, 80, "[]", "pending", now),
    )


# ---------------------------------------------------------------------------
# score_item — 正常 + 异常
# ---------------------------------------------------------------------------
def test_score_item_ok(client, temp_db):
    """正常写入 ai_scores，返回 score_id。"""
    _insert_hotspot("h-score-1", "AI 安全漏洞")
    res = client.post("/api/mcp/phase8/score-item", json={
        "hotspot_id": "h-score-1",
        "score": 8.5,
        "reason": "高影响力漏洞",
        "scorer": "agent:claude-desktop",
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "ok"
    assert isinstance(data["score_id"], int)

    # 验证 DB 中确实写入
    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM ai_scores WHERE hotspot_id = ?", ("h-score-1",)
    ).fetchone()
    assert row is not None
    assert row["score"] == 8.5
    assert row["scorer"] == "agent:claude-desktop"


def test_score_item_validation(client, temp_db):
    """score 超出 0-10 范围报错 422。"""
    _insert_hotspot("h-score-2", "测试")
    res = client.post("/api/mcp/phase8/score-item", json={
        "hotspot_id": "h-score-2",
        "score": 15.0,
        "scorer": "rule",
    })
    assert res.status_code == 422, res.text


# ---------------------------------------------------------------------------
# enrich_concept — 正常 + 异常
# ---------------------------------------------------------------------------
def test_enrich_concept_ok(client, temp_db, tmp_concept_dir):
    """正常写入 concepts/{name}.md。"""
    res = client.post("/api/mcp/phase8/enrich-concept", json={
        "concept_name": "zero-trust",
        "content": "Zero Trust 是一种安全模型...",
        "source": "manual",
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "ok"
    assert data["file"] == "concepts/zero-trust.md"

    # 验证文件确实写入
    filepath = os.path.join(tmp_concept_dir, "zero-trust.md")
    assert os.path.exists(filepath)
    content = open(filepath, encoding="utf-8").read()
    assert "title: zero-trust" in content
    assert "Zero Trust 是一种安全模型..." in content


def test_enrich_concept_missing_name(client, temp_db):
    """concept_name 为空报错 422。"""
    res = client.post("/api/mcp/phase8/enrich-concept", json={
        "concept_name": "",
        "content": "内容",
    })
    assert res.status_code == 422, res.text


# ---------------------------------------------------------------------------
# link_items — 正常 + 异常
# ---------------------------------------------------------------------------
def test_link_items_ok(client, temp_db):
    """正常写入 knowledge_links，返回 link_id。"""
    res = client.post("/api/mcp/phase8/link-items", json={
        "from_id": "item-a",
        "to_id": "item-b",
        "link_type": "similar",
        "confidence": 0.85,
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "ok"
    assert isinstance(data["link_id"], int)

    # 验证 DB 中确实写入
    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM knowledge_links WHERE from_item_id = ?", ("item-a",)
    ).fetchone()
    assert row is not None
    assert row["to_item_id"] == "item-b"
    assert row["link_type"] == "similar"
    assert row["confidence"] == 0.85


def test_link_items_invalid_type(client, temp_db):
    """link_type 不合法报错 422。"""
    res = client.post("/api/mcp/phase8/link-items", json={
        "from_id": "item-a",
        "to_id": "item-b",
        "link_type": "invalid-type",
    })
    assert res.status_code == 422, res.text


# ---------------------------------------------------------------------------
# trigger_codegarden_drift — 正常 + 异常
# ---------------------------------------------------------------------------
def test_trigger_drift_ok(client, temp_db):
    """返回 drift_score（当前 stub）。"""
    res = client.post("/api/mcp/phase8/trigger-codegarden-drift", json={
        "project_id": "proj-42",
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "ok"
    assert data["drift_score"] == 0.0


def test_trigger_drift_missing_project(client, temp_db):
    """project_id 为空报错 422。"""
    res = client.post("/api/mcp/phase8/trigger-codegarden-drift", json={
        "project_id": "",
    })
    assert res.status_code == 422, res.text
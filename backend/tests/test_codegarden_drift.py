"""Phase 14 测试 — tech_stack_drift 评估服务.

测试用例 (spec §6.1):
1. test_drift_detect_new_tech — 发现新 tech 时生成评估记录
2. test_drift_no_matching_project — 无匹配项目时跳过
3. test_drift_already_matched — 已匹配的 tech 不重复评估
4. test_drift_status_update — 评估状态可更新
5. test_drift_api_endpoint — POST /api/codegarden/drift/assess 返回报告
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from backend.services.codegarden_drift import (
    assess_drift,
    get_assessments,
    update_assessment_status,
    VALID_DRIFT_STATUSES,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def drift_conn(tmp_path: Path) -> sqlite3.Connection:
    """创建独立的 SQLite 内存数据库, 建好所需的表."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")

    # 建 cg_drift_assessments 表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cg_drift_assessments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id      TEXT NOT NULL,
            tech_name       TEXT NOT NULL,
            source_item_id  TEXT,
            source_domain   TEXT,
            status          TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
                                'pending', 'reviewed', 'applied', 'dismissed'
                            )),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            reviewed_at     TEXT,
            notes           TEXT,
            UNIQUE(project_id, tech_name)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cg_drift_status ON cg_drift_assessments(status)")

    # 建 cg_projects 表 (最小子集)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cg_projects (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            display_name    TEXT,
            tech_stack      TEXT,
            lifecycle_stage TEXT DEFAULT 'active'
        )
    """)

    # 建 knowledge_items 表 (最小子集)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_items (
            id              TEXT PRIMARY KEY,
            title           TEXT,
            domain          TEXT,
            type            TEXT DEFAULT 'article'
        )
    """)

    # 建 item_entities 表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_entities (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id         TEXT NOT NULL,
            entity_name     TEXT NOT NULL,
            entity_type     TEXT NOT NULL CHECK(entity_type IN (
                                'concept','tool','vendor','person','cve',
                                'technique','standard','event'
                            )),
            confidence      REAL DEFAULT 1.0,
            source          TEXT DEFAULT 'rule',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(item_id, entity_name, entity_type)
        )
    """)

    yield conn
    conn.close()


def _patch_conn(monkeypatch: Any, conn: sqlite3.Connection) -> None:
    """用 monkeypatch 把 get_connection 替换为我们的测试连接."""

    def _fake_conn():
        return conn

    monkeypatch.setattr("backend.services.codegarden_drift.get_connection", _fake_conn)


# ---------------------------------------------------------------------------
# 1. 发现新 tech 时生成评估记录
# ---------------------------------------------------------------------------
def test_drift_detect_new_tech(drift_conn: sqlite3.Connection, monkeypatch: Any) -> None:
    _patch_conn(monkeypatch, drift_conn)

    # 准备测试数据
    drift_conn.execute("INSERT INTO cg_projects (id, name, display_name, tech_stack, lifecycle_stage) VALUES (?, ?, ?, ?, ?)",
                       ("p1", "test-project", "Test Project", '["fastapi", "react"]', "active"))
    drift_conn.execute("INSERT INTO knowledge_items (id, title, domain) VALUES (?, ?, ?)",
                       ("k1", "FastAPI Tutorial", "ai"))
    # item_entities: entity_type='tool' 的 tech
    drift_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                       ("k1", "fastapi", "tool"))
    drift_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                       ("k1", "react", "tool"))

    report = assess_drift()

    assert report["matched_count"] == 2, f"expected 2 matched, got {report['matched_count']}"
    assert len(report["new_techs"]) == 2
    assert len(report["affected_projects"]) == 1
    assert report["affected_projects"][0]["project_id"] == "p1"
    assert "fastapi" in report["affected_projects"][0]["techs"]
    assert "react" in report["affected_projects"][0]["techs"]

    # 验证 cg_drift_assessments 有记录
    rows = drift_conn.execute("SELECT * FROM cg_drift_assessments").fetchall()
    assert len(rows) == 2
    assert rows[0]["status"] == "pending"


# ---------------------------------------------------------------------------
# 2. 无匹配项目时跳过
# ---------------------------------------------------------------------------
def test_drift_no_matching_project(drift_conn: sqlite3.Connection, monkeypatch: Any) -> None:
    _patch_conn(monkeypatch, drift_conn)

    drift_conn.execute("INSERT INTO cg_projects (id, name, display_name, tech_stack, lifecycle_stage) VALUES (?, ?, ?, ?, ?)",
                       ("p1", "test-project", "Test Project", '["fastapi"]', "active"))
    drift_conn.execute("INSERT INTO knowledge_items (id, title, domain) VALUES (?, ?, ?)",
                       ("k1", "Some Article", "ai"))
    # entity_type='tool' 但 tech 不在任何项目的 tech_stack 中
    drift_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                       ("k1", "unknown-tool", "tool"))

    report = assess_drift()

    assert report["matched_count"] == 0
    assert len(report["new_techs"]) == 0
    assert len(report["affected_projects"]) == 0
    assert "unknown-tool" in report["skipped_no_project"]


# ---------------------------------------------------------------------------
# 3. 已匹配的 tech 不重复评估
# ---------------------------------------------------------------------------
def test_drift_already_matched(drift_conn: sqlite3.Connection, monkeypatch: Any) -> None:
    _patch_conn(monkeypatch, drift_conn)

    drift_conn.execute("INSERT INTO cg_projects (id, name, display_name, tech_stack, lifecycle_stage) VALUES (?, ?, ?, ?, ?)",
                       ("p1", "test-project", "Test Project", '["fastapi"]', "active"))
    drift_conn.execute("INSERT INTO knowledge_items (id, title, domain) VALUES (?, ?, ?)",
                       ("k1", "FastAPI Article", "ai"))
    drift_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                       ("k1", "fastapi", "tool"))

    # 第一次评估
    report1 = assess_drift()
    assert report1["matched_count"] == 1

    # 第二次评估 (不应重复插入)
    report2 = assess_drift()
    assert report2["matched_count"] == 0  # 已存在, 不重复插入

    # 验证 cg_drift_assessments 只有一条记录
    rows = drift_conn.execute("SELECT * FROM cg_drift_assessments").fetchall()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# 4. 评估状态可更新
# ---------------------------------------------------------------------------
def test_drift_status_update(drift_conn: sqlite3.Connection, monkeypatch: Any) -> None:
    _patch_conn(monkeypatch, drift_conn)

    drift_conn.execute("INSERT INTO cg_projects (id, name, display_name, tech_stack, lifecycle_stage) VALUES (?, ?, ?, ?, ?)",
                       ("p1", "test-project", "Test Project", '["fastapi"]', "active"))
    drift_conn.execute("INSERT INTO knowledge_items (id, title, domain) VALUES (?, ?, ?)",
                       ("k1", "FastAPI Article", "ai"))
    drift_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                       ("k1", "fastapi", "tool"))
    assess_drift()

    # 更新状态为 applied
    updated = update_assessment_status(assessment_id=1, status="applied", notes="已应用到项目")
    assert updated is not None
    assert updated["status"] == "applied"
    assert updated["notes"] == "已应用到项目"
    assert updated["reviewed_at"] is not None

    # 更新状态为 dismissed
    updated2 = update_assessment_status(assessment_id=1, status="dismissed")
    assert updated2 is not None
    assert updated2["status"] == "dismissed"

    # 无效状态
    with pytest.raises(ValueError):
        update_assessment_status(assessment_id=1, status="invalid")


# ---------------------------------------------------------------------------
# 5. 验证 API 端点返回报告
# ---------------------------------------------------------------------------
def test_drift_api_endpoint(drift_conn: sqlite3.Connection, monkeypatch: Any) -> None:
    """测试 assess_drift 返回的报告格式正确."""
    _patch_conn(monkeypatch, drift_conn)

    drift_conn.execute("INSERT INTO cg_projects (id, name, display_name, tech_stack, lifecycle_stage) VALUES (?, ?, ?, ?, ?)",
                       ("p1", "test-project", "Test Project", '["fastapi"]', "active"))
    drift_conn.execute("INSERT INTO knowledge_items (id, title, domain) VALUES (?, ?, ?)",
                       ("k1", "FastAPI Article", "ai"))
    drift_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                       ("k1", "fastapi", "tool"))

    report = assess_drift()

    # 验证报告格式
    assert "new_techs" in report
    assert "affected_projects" in report
    assert "matched_count" in report
    assert "skipped_no_project" in report
    assert isinstance(report["new_techs"], list)
    assert isinstance(report["affected_projects"], list)
    assert isinstance(report["matched_count"], int)
    assert isinstance(report["skipped_no_project"], list)

    # 验证 get_assessments 返回列表
    assessments = get_assessments()
    assert assessments["total"] == 1
    assert len(assessments["items"]) == 1
    assert assessments["items"][0]["project_id"] == "p1"
    assert assessments["items"][0]["tech_name"] == "fastapi"

    # 验证筛选
    pending = get_assessments(status="pending")
    assert pending["total"] == 1
    dismissed = get_assessments(status="dismissed")
    assert dismissed["total"] == 0
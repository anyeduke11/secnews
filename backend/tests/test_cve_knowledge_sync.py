"""Phase 14 测试 — CVE 双向同步服务.

测试用例 (spec §6.2):
1. test_sync_new_cve — 新 CVE 插入 security_entities
2. test_sync_existing_cve — 已存在的 CVE 跳过
3. test_sync_update_metadata — 已有 CVE 更新 knowledge_ref
4. test_sync_no_duplicate — 同 CVE 不重复插入
5. test_sync_api_endpoint — POST /api/cve/sync 返回报告
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from backend.services.cve_knowledge_sync import sync_cve_to_security

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cve_conn(tmp_path: Path) -> sqlite3.Connection:
    """创建独立的 SQLite 内存数据库."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")

    # 建 item_entities 表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_entities (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id         TEXT NOT NULL,
            entity_name     TEXT NOT NULL,
            entity_type     TEXT NOT NULL,
            confidence      REAL DEFAULT 1.0,
            source          TEXT DEFAULT 'rule',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(item_id, entity_name, entity_type)
        )
    """)

    # 建 security_entities 表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS security_entities (
            id          TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            name        TEXT NOT NULL,
            description TEXT,
            external_ref TEXT,
            metadata    TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_security_entities_type ON security_entities(entity_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_security_entities_name ON security_entities(name)")

    yield conn
    conn.close()


def _patch_conn(monkeypatch: Any, conn: sqlite3.Connection) -> None:
    """用 monkeypatch 把 get_connection 替换为我们的测试连接."""

    def _fake_conn():
        return conn

    monkeypatch.setattr("backend.services.cve_knowledge_sync.get_connection", _fake_conn)


# ---------------------------------------------------------------------------
# 1. 新 CVE 插入 security_entities
# ---------------------------------------------------------------------------
def test_sync_new_cve(cve_conn: sqlite3.Connection, monkeypatch: Any) -> None:
    _patch_conn(monkeypatch, cve_conn)

    # 准备测试数据: item_entities 中有两个 CVE
    cve_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                     ("k1", "CVE-2024-12345", "cve"))
    cve_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                     ("k1", "CVE-2024-67890", "cve"))

    report = sync_cve_to_security()

    assert report["synced"] == 2
    assert report["already_exists"] == 0
    assert report["updated"] == 0
    assert report["failed"] == 0
    assert report["total_processed"] == 2

    # 验证 security_entities 有记录
    rows = cve_conn.execute("SELECT * FROM security_entities WHERE entity_type='cve'").fetchall()
    assert len(rows) == 2
    names = {r["name"] for r in rows}
    assert "CVE-2024-12345" in names
    assert "CVE-2024-67890" in names

    # 验证 metadata 有 knowledge_refs
    for r in rows:
        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        assert "knowledge_refs" in meta
        assert len(meta["knowledge_refs"]) == 1
        assert meta["knowledge_refs"][0] == "k1"


# ---------------------------------------------------------------------------
# 2. 已存在的 CVE 跳过
# ---------------------------------------------------------------------------
def test_sync_existing_cve(cve_conn: sqlite3.Connection, monkeypatch: Any) -> None:
    _patch_conn(monkeypatch, cve_conn)

    # 准备: security_entities 中已有 CVE-2024-12345, 且 knowledge_refs 已包含 k1
    cve_conn.execute("INSERT INTO security_entities (id, entity_type, name, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                     ("CVE-2024-12345", "cve", "CVE-2024-12345", '{"knowledge_refs": ["k1"]}',
                      "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"))
    cve_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                     ("k1", "CVE-2024-12345", "cve"))

    report = sync_cve_to_security()

    assert report["synced"] == 0
    assert report["already_exists"] == 1  # 已存在且 knowledge_refs 已包含 k1, 无需更新
    assert report["updated"] == 0
    assert report["total_processed"] == 1


# ---------------------------------------------------------------------------
# 3. 已有 CVE 更新 knowledge_ref
# ---------------------------------------------------------------------------
def test_sync_update_metadata(cve_conn: sqlite3.Connection, monkeypatch: Any) -> None:
    _patch_conn(monkeypatch, cve_conn)

    # security_entities 中已有 CVE-2024-12345, 但 metadata 只有 k1
    cve_conn.execute("INSERT INTO security_entities (id, entity_type, name, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                     ("CVE-2024-12345", "cve", "CVE-2024-12345",
                      json.dumps({"knowledge_refs": ["k1"]}),
                      "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"))

    # item_entities 中有 k1 和 k2 都引用了这个 CVE
    cve_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                     ("k1", "CVE-2024-12345", "cve"))
    cve_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                     ("k2", "CVE-2024-12345", "cve"))

    report = sync_cve_to_security()

    assert report["synced"] == 0
    assert report["already_exists"] == 0
    assert report["updated"] == 1  # metadata 已更新
    assert report["total_processed"] == 2

    # 验证 metadata 已包含 k2
    row = cve_conn.execute("SELECT metadata FROM security_entities WHERE id = ?",
                           ("CVE-2024-12345",)).fetchone()
    meta = json.loads(row["metadata"]) if row["metadata"] else {}
    assert "k2" in meta["knowledge_refs"]
    assert len(meta["knowledge_refs"]) == 2  # k1, k2


# ---------------------------------------------------------------------------
# 4. 同 CVE 不重复插入
# ---------------------------------------------------------------------------
def test_sync_no_duplicate(cve_conn: sqlite3.Connection, monkeypatch: Any) -> None:
    _patch_conn(monkeypatch, cve_conn)

    # 多次同步同一 CVE
    cve_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                     ("k1", "CVE-2024-12345", "cve"))

    report1 = sync_cve_to_security()
    assert report1["synced"] == 1

    report2 = sync_cve_to_security()
    assert report2["synced"] == 0
    assert report2["already_exists"] == 1

    # security_entities 只有一条记录
    rows = cve_conn.execute("SELECT * FROM security_entities WHERE entity_type='cve'").fetchall()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# 5. 验证 API 端点返回报告
# ---------------------------------------------------------------------------
def test_sync_api_endpoint(cve_conn: sqlite3.Connection, monkeypatch: Any) -> None:
    """测试 sync_cve_to_security 返回的报告格式正确."""
    _patch_conn(monkeypatch, cve_conn)

    cve_conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                     ("k1", "CVE-2024-12345", "cve"))

    report = sync_cve_to_security()

    # 验证报告格式
    assert "synced" in report
    assert "already_exists" in report
    assert "updated" in report
    assert "failed" in report
    assert "total_processed" in report
    assert isinstance(report["synced"], int)
    assert isinstance(report["already_exists"], int)
    assert isinstance(report["updated"], int)
    assert isinstance(report["failed"], int)
    assert isinstance(report["total_processed"], int)
    assert report["synced"] == 1
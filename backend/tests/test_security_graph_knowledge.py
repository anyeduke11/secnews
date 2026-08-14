"""Phase 14 测试 — Security Graph 引用 Knowledge.

测试用例 (spec §6.4):
1. test_cve_node_knowledge_ref — CVE 节点含 knowledge_ref 属性
2. test_knowledge_edge_created — knowledge 与 security 间有边
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from backend.security.graph import SecurityGraphEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def graph_conn(monkeypatch: Any) -> sqlite3.Connection:
    """创建独立的 SQLite 内存数据库, 建好所需的表和数据."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")

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

    # 建 security_edges 表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS security_edges (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id   TEXT NOT NULL,
            target_id   TEXT NOT NULL,
            edge_type   TEXT NOT NULL,
            weight      REAL DEFAULT 1.0,
            metadata    TEXT,
            created_at  TEXT NOT NULL
        )
    """)

    # 建 knowledge_items 表 (最小子集)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_items (
            id          TEXT PRIMARY KEY,
            title       TEXT,
            source      TEXT,
            domain      TEXT,
            type        TEXT,
            cve_ids     TEXT,
            attack_techniques TEXT,
            compliance_refs   TEXT
        )
    """)

    # 插入测试数据: security_entities 中有 CVE 节点 (含 knowledge_refs)
    conn.execute(
        "INSERT INTO security_entities (id, entity_type, name, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("CVE-2024-12345", "cve", "CVE-2024-12345",
         json.dumps({"knowledge_refs": ["k1", "k2"]}),
         "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO security_entities (id, entity_type, name, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("CVE-2024-67890", "cve", "CVE-2024-67890",
         json.dumps({"knowledge_refs": []}),
         "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO security_entities (id, entity_type, name, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("CVE-2024-99999", "cve", "CVE-2024-99999",
         None,  # 无 metadata
         "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    )

    # 插入 knowledge_items
    conn.execute(
        "INSERT INTO knowledge_items (id, title, source, domain, type, cve_ids) VALUES (?, ?, ?, ?, ?, ?)",
        ("k1", "Article about CVE-2024-12345", "test", "security", "article",
         json.dumps(["CVE-2024-12345"])),
    )

    # monkeypatch get_connection
    def _fake_conn():
        return conn
    monkeypatch.setattr("backend.security.graph.get_connection", _fake_conn)

    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# 1. CVE 节点含 knowledge_ref 属性
# ---------------------------------------------------------------------------
def test_cve_node_knowledge_ref(graph_conn: sqlite3.Connection) -> None:
    """验证 CVE 节点含 knowledge_refs, knowledge_count, linked 属性."""
    engine = SecurityGraphEngine()
    nodes = engine._load_cve_nodes()

    # 找到三个 CVE 节点
    cve_nodes = {n["name"]: n for n in nodes}

    # 有 knowledge_refs 的 CVE
    cve1 = cve_nodes.get("CVE-2024-12345")
    assert cve1 is not None
    assert "knowledge_refs" in cve1
    assert "knowledge_count" in cve1
    assert "linked" in cve1
    assert cve1["knowledge_count"] == 2
    assert cve1["linked"] is True
    assert "k1" in cve1["knowledge_refs"]
    assert "k2" in cve1["knowledge_refs"]

    # 空 knowledge_refs 的 CVE
    cve2 = cve_nodes.get("CVE-2024-67890")
    assert cve2 is not None
    assert cve2["knowledge_count"] == 0
    assert cve2["linked"] is False

    # 无 metadata 的 CVE
    cve3 = cve_nodes.get("CVE-2024-99999")
    assert cve3 is not None
    assert cve3["knowledge_count"] == 0
    assert cve3["linked"] is False


# ---------------------------------------------------------------------------
# 2. knowledge 与 security 间有 references 边
# ---------------------------------------------------------------------------
def test_knowledge_edge_created(graph_conn: sqlite3.Connection) -> None:
    """验证 knowledge_item 与 security_entity 之间有 references 类型的边."""
    engine = SecurityGraphEngine()

    # 构建 knowledge_item 节点
    kn_nodes = engine._load_knowledge_item_nodes()
    edges = engine._build_knowledge_edges(kn_nodes)

    # 找到 references 类型的边
    ref_edges = [e for e in edges if e["edge_type"] == "references"]
    assert len(ref_edges) >= 1, f"expected at least 1 references edge, got {len(ref_edges)}"

    # 验证边指向正确的 security_entity
    ref_edge = ref_edges[0]
    assert ref_edge["source_id"] == "k1"
    assert ref_edge["target_id"] == "CVE-2024-12345"
    assert ref_edge["edge_type"] == "references"
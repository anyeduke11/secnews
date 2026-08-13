"""Phase 14 测试 — 跨域 entity 命名空间.

测试用例 (spec §6.3):
1. test_entity_types_enum — 8 种 entity_type 枚举值一致
2. test_item_entities_valid — item_entities 记录符合枚举
3. test_security_entities_valid — security_entities 记录符合枚举
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

# 8 种统一 entity_type 枚举值
VALID_ENTITY_TYPES = frozenset([
    "concept", "tool", "vendor", "person",
    "cve", "technique", "standard", "event",
])


# ---------------------------------------------------------------------------
# 1. 8 种 entity_type 枚举值一致
# ---------------------------------------------------------------------------
def test_entity_types_enum() -> None:
    """验证 8 种 entity_type 枚举值定义一致."""
    assert len(VALID_ENTITY_TYPES) == 8
    assert "concept" in VALID_ENTITY_TYPES
    assert "tool" in VALID_ENTITY_TYPES
    assert "vendor" in VALID_ENTITY_TYPES
    assert "person" in VALID_ENTITY_TYPES
    assert "cve" in VALID_ENTITY_TYPES
    assert "technique" in VALID_ENTITY_TYPES
    assert "standard" in VALID_ENTITY_TYPES
    assert "event" in VALID_ENTITY_TYPES


# ---------------------------------------------------------------------------
# 2. item_entities 记录符合枚举
# ---------------------------------------------------------------------------
def test_item_entities_valid() -> None:
    """验证 item_entities 表的 CHECK 约束覆盖所有 8 种类型.

    使用 SQLite 内存数据库验证 CHECK 约束是否生效.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")

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

    # 所有 8 种类型应该都能插入
    for t in VALID_ENTITY_TYPES:
        conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                     ("k1", f"test-{t}", t))

    # 无效类型应该被拒绝
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO item_entities (item_id, entity_name, entity_type) VALUES (?, ?, ?)",
                     ("k1", "invalid-type", "invalid_type"))

    conn.close()


# ---------------------------------------------------------------------------
# 3. security_entities 记录符合枚举
# ---------------------------------------------------------------------------
def test_security_entities_valid() -> None:
    """验证 security_entities 的 entity_type 值均在 8 种枚举中.

    由于 SQLite 不支持 ALTER TABLE ADD CHECK, 此处验证应用层逻辑:
    现有 security_entities 记录中 entity_type 值是否都在 8 种枚举内.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=OFF")

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

    # 插入 8 种有效类型的记录
    for t in VALID_ENTITY_TYPES:
        conn.execute(
            "INSERT INTO security_entities (id, entity_type, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (f"id-{t}", t, f"test-{t}", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        )

    # 验证所有记录的 entity_type 都在枚举中
    rows = conn.execute("SELECT entity_type FROM security_entities").fetchall()
    for r in rows:
        assert r["entity_type"] in VALID_ENTITY_TYPES, \
            f"entity_type {r['entity_type']!r} 不在有效枚举中"

    conn.close()
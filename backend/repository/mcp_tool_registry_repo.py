"""MCPToolRegistryRepository — mcp_tool_registry 表数据访问 (v1.7 Phase 7).

Batch 2 D (api 层 SQL 下沉): ``backend/api/mcp_config.py`` 的 seeding 与
list 查询 SQL 收拢到 repo 层。schema 序列化 (Pydantic model_json_schema →
JSON) 留在 api 层 — 那是 MCP tool 元数据领域逻辑, repo 只认已备好的行。

约定: 单例模式 (与 knowledge_repo 等一致), 全公开方法同步, 依赖
:func:`backend.repository.db.get_connection` (thread-local, autocommit;
commit 为显式兜底, 与原实现一致)。
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from typing import Any

from backend.repository.db import get_connection


class MCPToolRegistryRepository:
    """CRUD for the ``mcp_tool_registry`` table."""

    def seed(self, rows: Iterable[tuple[str, str, str, str, str, str]]) -> int:
        """INSERT OR IGNORE 幂等写入 (name PRIMARY KEY 保证)。

        Args:
            rows: (name, category, description, input_schema_json,
                version, created_at) 六元组序列。

        Returns: 实际写入的条数 (首次 = len(rows), 重复启动 = 0)。
        """
        conn = get_connection()
        inserted = 0
        for name, category, description, input_schema_json, version, created_at in rows:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO mcp_tool_registry
                    (name, category, description, input_schema, enabled, version, created_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (name, category, description, input_schema_json, version, created_at),
            )
            if cur.rowcount > 0:
                inserted += 1
        conn.commit()
        return inserted

    def list_tools(self, enabled_only: bool = False) -> list[sqlite3.Row]:
        """读 tool 元数据原始行 (category, name 排序); schema 反序列化由调用方做。"""
        conn = get_connection()
        sql = (
            "SELECT name, category, description, input_schema, enabled, version, "
            "created_at FROM mcp_tool_registry"
        )
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY category, name"
        return conn.execute(sql).fetchall()


mcp_tool_registry_repo = MCPToolRegistryRepository()


def _row_to_tool(r: sqlite3.Row) -> dict[str, Any]:
    """input_schema JSON → dict (坏 schema 显 {} 不抛)。"""
    try:
        schema = json.loads(r["input_schema"]) if r["input_schema"] else {}
    except Exception:
        schema = {}
    return {
        "name": r["name"],
        "category": r["category"],
        "description": r["description"],
        "input_schema": schema,
        "enabled": bool(r["enabled"]),
        "version": r["version"],
        "created_at": r["created_at"],
    }


__all__ = ["MCPToolRegistryRepository", "_row_to_tool", "mcp_tool_registry_repo"]

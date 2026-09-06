"""v1.0 T13 KnowledgeRevisionRepository — append-only revision 行."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.repository.db import get_connection


class KnowledgeRevisionRepository:
    """append-only: 每次 publish/deprecate/retract 留 revision 行 (wiki_path 不可变写)."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    def append(self, r: dict[str, Any]) -> int:
        cur = self._c().execute(
            "INSERT INTO v1_knowledge_revisions "
            "(knowledge_id, revision, status, reason, wiki_path, content_hash, recorded_at, recorded_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                r["knowledge_id"], r["revision"], r["status"], r.get("reason"),
                r.get("wiki_path"), r.get("content_hash"),
                r.get("recorded_at"), r.get("recorded_by", "user"),
            ),
        )
        self._c().commit()
        return cur.lastrowid or 0

    def list_by_knowledge(self, knowledge_id: str) -> list[dict[str, Any]]:
        rows = self._c().execute(
            "SELECT * FROM v1_knowledge_revisions WHERE knowledge_id = ? "
            "ORDER BY revision DESC",
            (knowledge_id,),
        ).fetchall()
        return [dict(r) for r in rows]


class KnowledgeRefRepository:
    """v1_knowledge_refs 引用关联 — SK-05 ReuseReceipt 派生基础."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    def _c(self) -> sqlite3.Connection:
        return self._conn or get_connection()

    def add(self, knowledge_id: str, source_type: str, source_id: str, role: str = "used") -> bool:
        """幂等: 重复 (k, st, sid, role) 不重复."""
        try:
            self._c().execute(
                "INSERT OR IGNORE INTO v1_knowledge_refs "
                "(knowledge_id, source_type, source_id, role, created_at) "
                "VALUES (?, ?, ?, ?, datetime('now', 'localtime'))",
                (knowledge_id, source_type, source_id, role),
            )
            self._c().commit()
            return True
        except Exception:
            self._c().rollback()
            return False

    def count_by_knowledge(self, knowledge_id: str) -> dict[str, Any]:
        """§9.4 复用记录 — 派生: by_judgment / by_action / total / recent_30d."""
        conn = self._c()
        # by_judgment / by_action (artifact 走 action 引用间接, T13 不展开)
        by_judgment = conn.execute(
            "SELECT COUNT(*) FROM v1_knowledge_refs WHERE knowledge_id = ? AND source_type = 'judgment'",
            (knowledge_id,),
        ).fetchone()[0]
        by_action = conn.execute(
            "SELECT COUNT(*) FROM v1_knowledge_refs WHERE knowledge_id = ? AND source_type = 'action'",
            (knowledge_id,),
        ).fetchone()[0]
        recent_30d = conn.execute(
            "SELECT COUNT(*) FROM v1_knowledge_refs "
            "WHERE knowledge_id = ? AND created_at >= datetime('now', '-30 days')",
            (knowledge_id,),
        ).fetchone()[0]
        return {
            "total": by_judgment + by_action,
            "by_judgment": by_judgment,
            "by_action": by_action,
            "recent_30d": recent_30d,
        }

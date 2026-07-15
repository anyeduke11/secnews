"""Knowledge repository — SQLite access for knowledge items, concepts, tasks.

Design notes
------------
- ``get_connection()`` returns a thread-local ``sqlite3.Connection`` in
  **autocommit** mode (``isolation_level=None``), so single statements
  are committed automatically — no manual ``conn.commit()`` needed.
- Multi-statement transactions would require explicit ``BEGIN``/``COMMIT``,
  but every method here issues a single SQL statement.
- SQL column ``mastery`` maps to model field ``KnowledgeItem.mastered``
  (see ``from_row`` in ``knowledge_models.py``).
"""
from __future__ import annotations

import json
from typing import Optional

from backend.domain.knowledge_models import (
    KnowledgeConcept,
    KnowledgeItem,
    KnowledgeTask,
    now_iso,
)
from backend.repository.db import get_connection


class KnowledgeRepo:
    """CRUD + query for knowledge_items, knowledge_concepts, knowledge_tasks."""

    # ── Knowledge Items ──────────────────────────────────────────

    def upsert_item(self, item: KnowledgeItem) -> None:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO knowledge_items (id, title, source, source_url, domain,
                topic, type, difficulty, tags, concepts, mastery, compiled,
                ingested_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                source=excluded.source,
                source_url=excluded.source_url,
                domain=excluded.domain,
                topic=excluded.topic,
                type=excluded.type,
                difficulty=excluded.difficulty,
                tags=excluded.tags,
                concepts=excluded.concepts,
                mastery=excluded.mastery,
                compiled=excluded.compiled,
                updated_at=excluded.updated_at
            """,
            (
                item.id,
                item.title,
                item.source,
                item.source_url,
                item.domain,
                item.topic,
                item.type,
                item.difficulty,
                json.dumps(item.tags),
                json.dumps(item.concepts),
                item.mastered,
                int(item.compiled),
                item.ingested_at,
                item.updated_at,
            ),
        )

    def get_item(self, item_id: str) -> Optional[KnowledgeItem]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM knowledge_items WHERE id = ?", (item_id,)
        ).fetchone()
        return KnowledgeItem.from_row(dict(row)) if row else None

    def list_items(
        self,
        domain: Optional[str] = None,
        source: Optional[str] = None,
        compiled: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KnowledgeItem]:
        conn = get_connection()
        where = ["1=1"]
        params: list = []
        if domain:
            where.append("domain = ?")
            params.append(domain)
        if source:
            where.append("source = ?")
            params.append(source)
        if compiled is not None:
            where.append("compiled = ?")
            params.append(int(compiled))
        sql = (
            "SELECT * FROM knowledge_items WHERE "
            + " AND ".join(where)
            + " ORDER BY ingested_at DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [KnowledgeItem.from_row(dict(r)) for r in rows]

    def count_items(
        self,
        domain: Optional[str] = None,
        compiled: Optional[bool] = None,
    ) -> int:
        conn = get_connection()
        where = ["1=1"]
        params: list = []
        if domain:
            where.append("domain = ?")
            params.append(domain)
        if compiled is not None:
            where.append("compiled = ?")
            params.append(int(compiled))
        sql = f"SELECT COUNT(*) FROM knowledge_items WHERE {' AND '.join(where)}"
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else 0

    def count_orphan_items(self) -> int:
        """无 concepts 关联的 items 数量。"""
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) FROM knowledge_items WHERE concepts IS NULL OR concepts = '[]'"
        ).fetchone()
        return row[0] if row else 0

    def count_stale_concepts(self, days: int = 30) -> int:
        """超过 N 天未更新的 concepts 数量。

        用 datetime() 转换以兼容 ISO 8601 带时区格式（如
        ``2026-07-15T10:00:00+00:00``）与 SQLite 内置 ``datetime('now')``
        的 ``YYYY-MM-DD HH:MM:SS`` 格式。
        """
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) FROM knowledge_concepts "
            "WHERE datetime(updated_at) < datetime('now', ?)",
            (f'-{days} days',),
        ).fetchone()
        return row[0] if row else 0

    def domain_coverage(self) -> list[dict]:
        """按 domain 分组统计覆盖度。"""
        conn = get_connection()
        rows = conn.execute("""
            SELECT
                COALESCE(domain, 'unknown') as domain,
                COUNT(*) as total,
                SUM(CASE WHEN compiled = 1 THEN 1 ELSE 0 END) as compiled
            FROM knowledge_items
            GROUP BY COALESCE(domain, 'unknown')
        """).fetchall()
        return [
            {"domain": r[0], "total": r[1], "compiled": r[2],
             "coverage": r[2]/r[1] if r[1] > 0 else 0}
            for r in rows
        ]

    def delete_item(self, item_id: str) -> None:
        conn = get_connection()
        conn.execute("DELETE FROM knowledge_items WHERE id = ?", (item_id,))

    # ── Knowledge Concepts ───────────────────────────────────────

    def upsert_concept(self, concept: KnowledgeConcept) -> None:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO knowledge_concepts (slug, title, domain, source_items,
                local_wiki_ref, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                title=excluded.title,
                domain=excluded.domain,
                source_items=excluded.source_items,
                local_wiki_ref=excluded.local_wiki_ref,
                updated_at=excluded.updated_at
            """,
            (
                concept.slug,
                concept.title,
                concept.domain,
                json.dumps(concept.source_items),
                concept.local_wiki_ref,
                concept.updated_at,
            ),
        )

    def list_concepts(self, domain: Optional[str] = None) -> list[KnowledgeConcept]:
        conn = get_connection()
        if domain:
            rows = conn.execute(
                "SELECT * FROM knowledge_concepts WHERE domain = ? ORDER BY updated_at DESC",
                (domain,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM knowledge_concepts ORDER BY updated_at DESC"
            ).fetchall()
        return [KnowledgeConcept.from_row(dict(r)) for r in rows]

    # ── Knowledge Tasks ──────────────────────────────────────────

    def create_task(self, task_type: str, params: Optional[dict] = None) -> KnowledgeTask:
        conn = get_connection()
        now = now_iso()
        cursor = conn.execute(
            """
            INSERT INTO knowledge_tasks (task_type, status, params, created_at, updated_at)
            VALUES (?, 'pending', ?, ?, ?)
            """,
            (task_type, json.dumps(params) if params else None, now, now),
        )
        return KnowledgeTask(
            id=cursor.lastrowid,
            task_type=task_type,
            status="pending",
            params=params,
            created_at=now,
            updated_at=now,
        )

    def list_tasks(self, status: Optional[str] = None) -> list[KnowledgeTask]:
        conn = get_connection()
        if status:
            rows = conn.execute(
                "SELECT * FROM knowledge_tasks WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM knowledge_tasks ORDER BY created_at DESC"
            ).fetchall()
        return [KnowledgeTask.from_row(dict(r)) for r in rows]

    def update_task_status(
        self,
        task_id: int,
        status: str,
        result_path: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        conn = get_connection()
        conn.execute(
            """
            UPDATE knowledge_tasks
            SET status = ?, result_path = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, result_path, error_message, now_iso(), task_id),
        )


# Singleton
knowledge_repo = KnowledgeRepo()

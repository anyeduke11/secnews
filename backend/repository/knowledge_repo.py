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
        topic: Optional[str] = None,
        item_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
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
        if topic:
            where.append("topic = ?")
            params.append(topic)
        if item_type:
            where.append("type = ?")
            params.append(item_type)
        if difficulty:
            where.append("difficulty = ?")
            params.append(difficulty)
        if since:
            where.append("ingested_at >= ?")
            params.append(since)
        if until:
            # until 是日期，需要包含当天，所以用 < next day
            where.append("ingested_at < date(?, '+1 day')")
            params.append(until)
        sql = (
            "SELECT * FROM knowledge_items WHERE "
            + " AND ".join(where)
            + " ORDER BY ingested_at DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [KnowledgeItem.from_row(dict(r)) for r in rows]

    def list_topics(self, domain: Optional[str] = None) -> list[str]:
        """Return distinct topics, optionally filtered by domain."""
        conn = get_connection()
        if domain:
            rows = conn.execute(
                "SELECT DISTINCT topic FROM knowledge_items WHERE domain = ? AND topic IS NOT NULL",
                (domain,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT topic FROM knowledge_items WHERE topic IS NOT NULL"
            ).fetchall()
        return [r[0] for r in rows]

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

    def get_concept(self, slug: str) -> Optional[KnowledgeConcept]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM knowledge_concepts WHERE slug = ?", (slug,)
        ).fetchone()
        return KnowledgeConcept.from_row(dict(row)) if row else None

    def update_concept_local_wiki_ref(self, slug: str, ref: str) -> None:
        """Phase 1f Task 6.11: 回填 concept 的 local_wiki_ref 字段。"""
        conn = get_connection()
        conn.execute(
            "UPDATE knowledge_concepts SET local_wiki_ref = ?, updated_at = ? WHERE slug = ?",
            (ref, now_iso(), slug),
        )

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

    def list_tasks_by_type(
        self,
        task_type: str,
        params_filter: Optional[dict] = None,
    ) -> list[dict]:
        """List tasks by task_type, optionally filtered by params JSON keys.

        ``params_filter`` performs a LIKE match on the JSON ``params`` column.
        For ``{"draft_id": 5}`` it matches both ``"draft_id": 5`` and
        ``"draft_id":5`` to be tolerant of serialisation whitespace.
        """
        conn = get_connection()
        where = ["task_type = ?"]
        params: list = [task_type]
        if params_filter:
            for key, val in params_filter.items():
                where.append(
                    f"(params LIKE ? OR params LIKE ?)"
                )
                params.append(f'%"{key}": {val}%')
                params.append(f'%"{key}":{val}%')
        sql = (
            "SELECT * FROM knowledge_tasks WHERE "
            + " AND ".join(where)
            + " ORDER BY created_at DESC"
        )
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_task(self, id: int) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM knowledge_tasks WHERE id = ?", (id,)
        ).fetchone()
        return dict(row) if row else None

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

    # ── Content Calendar ─────────────────────────────────────────

    def upsert_calendar_entry(self, entry: dict) -> None:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO content_calendar (id, date, topic, type, status,
                source_items, draft_path, platform, published_url, stats,
                created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                date=excluded.date,
                topic=excluded.topic,
                type=excluded.type,
                status=excluded.status,
                source_items=excluded.source_items,
                draft_path=excluded.draft_path,
                platform=excluded.platform,
                published_url=excluded.published_url,
                stats=excluded.stats,
                updated_at=excluded.updated_at
            """,
            (
                entry.get("id"),
                entry["date"],
                entry["topic"],
                entry.get("type"),
                entry.get("status", "planned"),
                json.dumps(entry["source_items"]) if entry.get("source_items") else None,
                entry.get("draft_path"),
                entry.get("platform"),
                entry.get("published_url"),
                json.dumps(entry["stats"]) if entry.get("stats") else None,
                entry.get("created_at") or now_iso(),
                entry.get("updated_at") or now_iso(),
            ),
        )

    def get_calendar_entry(self, id: int) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM content_calendar WHERE id = ?", (id,)
        ).fetchone()
        return dict(row) if row else None

    def list_calendar_entries(self, year_month: Optional[str]) -> list[dict]:
        conn = get_connection()
        if year_month:
            rows = conn.execute(
                "SELECT * FROM content_calendar WHERE strftime('%Y-%m', date) = ? "
                "ORDER BY date ASC",
                (year_month,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM content_calendar ORDER BY date ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def update_calendar_entry(self, id: int, fields: dict) -> None:
        conn = get_connection()
        allowed = {
            "date", "topic", "type", "status", "source_items",
            "draft_path", "platform", "published_url", "stats",
        }
        sets: list[str] = []
        params: list = []
        for key in allowed:
            if key in fields:
                val = fields[key]
                if key in ("source_items", "stats") and val is not None:
                    val = json.dumps(val)
                sets.append(f"{key} = ?")
                params.append(val)
        if not sets:
            return
        sets.append("updated_at = ?")
        params.append(now_iso())
        params.append(id)
        conn.execute(
            f"UPDATE content_calendar SET {', '.join(sets)} WHERE id = ?",
            params,
        )

    def delete_calendar_entry(self, id: int) -> None:
        conn = get_connection()
        conn.execute("DELETE FROM content_calendar WHERE id = ?", (id,))

    # ── Content Drafts ───────────────────────────────────────────

    def upsert_draft(self, draft: dict) -> None:
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO content_drafts (id, file_path, title, status,
                calendar_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                file_path=excluded.file_path,
                title=excluded.title,
                status=excluded.status,
                calendar_id=excluded.calendar_id,
                updated_at=excluded.updated_at
            """,
            (
                draft.get("id"),
                draft["file_path"],
                draft["title"],
                draft.get("status", "draft"),
                draft.get("calendar_id"),
                draft.get("created_at") or now_iso(),
                draft.get("updated_at") or now_iso(),
            ),
        )

    def get_draft(self, id: int) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM content_drafts WHERE id = ?", (id,)
        ).fetchone()
        return dict(row) if row else None

    def list_drafts(
        self,
        status: Optional[str] = None,
        calendar_id: Optional[int] = None,
    ) -> list[dict]:
        conn = get_connection()
        where = ["1=1"]
        params: list = []
        if status:
            where.append("status = ?")
            params.append(status)
        if calendar_id is not None:
            where.append("calendar_id = ?")
            params.append(calendar_id)
        sql = (
            "SELECT * FROM content_drafts WHERE "
            + " AND ".join(where)
            + " ORDER BY updated_at DESC"
        )
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def update_draft(self, id: int, fields: dict) -> None:
        conn = get_connection()
        allowed = {"file_path", "title", "status", "calendar_id"}
        sets: list[str] = []
        params: list = []
        for key in allowed:
            if key in fields:
                sets.append(f"{key} = ?")
                params.append(fields[key])
        if not sets:
            return
        sets.append("updated_at = ?")
        params.append(now_iso())
        params.append(id)
        conn.execute(
            f"UPDATE content_drafts SET {', '.join(sets)} WHERE id = ?",
            params,
        )

    def delete_draft(self, id: int) -> None:
        conn = get_connection()
        conn.execute("DELETE FROM content_drafts WHERE id = ?", (id,))

    # ── Knowledge Plans ──────────────────────────────────────────

    def upsert_plan(self, plan_data: dict) -> None:
        """Insert or update a weekly learning plan.

        plan_data dict shape:
            {week, status?, plan_data: {goals, tasks}, created_at?}
        """
        conn = get_connection()
        existing = conn.execute(
            "SELECT id FROM knowledge_plans WHERE week = ?",
            (plan_data["week"],),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE knowledge_plans SET status = ?, plan_data = ? WHERE week = ?",
                (
                    plan_data.get("status", "active"),
                    json.dumps(plan_data["plan_data"]),
                    plan_data["week"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO knowledge_plans (week, status, plan_data, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    plan_data["week"],
                    plan_data.get("status", "active"),
                    json.dumps(plan_data["plan_data"]),
                    plan_data.get("created_at", now_iso()),
                ),
            )

    def get_plan(self, week: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM knowledge_plans WHERE week = ?", (week,)
        ).fetchone()
        if not row:
            return None
        r = dict(row)
        r["plan_data"] = json.loads(r["plan_data"])
        return r

    def list_plans(self, status: Optional[str] = None) -> list[dict]:
        conn = get_connection()
        if status:
            rows = conn.execute(
                "SELECT * FROM knowledge_plans WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM knowledge_plans ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["plan_data"] = json.loads(d["plan_data"])
            result.append(d)
        return result

    def update_plan_status(self, week: str, status: str) -> None:
        conn = get_connection()
        conn.execute(
            "UPDATE knowledge_plans SET status = ? WHERE week = ?",
            (status, week),
        )

    # ── Skill Config ─────────────────────────────────────────────

    def upsert_skill(self, skill: dict) -> None:
        """INSERT OR IGNORE a skill config (idempotent on skill_name)."""
        conn = get_connection()
        conn.execute(
            """
            INSERT OR IGNORE INTO knowledge_skill_config
                (skill_name, secret_id, model_override, prompt_template,
                 enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                skill["skill_name"],
                skill.get("secret_id"),
                skill.get("model_override"),
                skill.get("prompt_template"),
                int(skill.get("enabled", 1)),
                skill["created_at"],
                skill["updated_at"],
            ),
        )

    def get_skill(self, id: int) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM knowledge_skill_config WHERE id = ?", (id,)
        ).fetchone()
        return _skill_row_to_dict(row) if row else None

    def get_skill_by_name(self, skill_name: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM knowledge_skill_config WHERE skill_name = ?",
            (skill_name,),
        ).fetchone()
        return _skill_row_to_dict(row) if row else None

    def list_skills(self, enabled: Optional[bool] = None) -> list[dict]:
        conn = get_connection()
        if enabled is not None:
            rows = conn.execute(
                "SELECT * FROM knowledge_skill_config WHERE enabled = ? ORDER BY id",
                (int(enabled),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM knowledge_skill_config ORDER BY id"
            ).fetchall()
        return [_skill_row_to_dict(r) for r in rows]

    def update_skill(self, id: int, fields: dict) -> None:
        conn = get_connection()
        allowed = {
            "skill_name", "secret_id", "model_override",
            "prompt_template", "enabled",
        }
        sets: list[str] = []
        params: list = []
        for key in allowed:
            if key in fields:
                val = fields[key]
                if key == "enabled":
                    val = int(val)
                sets.append(f"{key} = ?")
                params.append(val)
        if not sets:
            return
        sets.append("updated_at = ?")
        params.append(now_iso())
        params.append(id)
        conn.execute(
            f"UPDATE knowledge_skill_config SET {', '.join(sets)} WHERE id = ?",
            params,
        )

    def delete_skill(self, id: int) -> None:
        conn = get_connection()
        conn.execute(
            "DELETE FROM knowledge_skill_config WHERE id = ?", (id,)
        )

    def count_skills(self) -> int:
        """Total skill_config rows — used to decide whether to seed."""
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) FROM knowledge_skill_config"
        ).fetchone()
        return row[0] if row else 0

    # ── Knowledge Progress ───────────────────────────────────────

    def upsert_progress(
        self,
        concept_slug: str,
        mastery: int,
        last_tested: Optional[str],
        test_count: int,
    ) -> None:
        """Insert or update mastery progress for a concept."""
        conn = get_connection()
        conn.execute(
            """
            INSERT INTO knowledge_progress
                (concept_slug, mastery, last_tested, test_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(concept_slug) DO UPDATE SET
                mastery=excluded.mastery,
                last_tested=excluded.last_tested,
                test_count=excluded.test_count,
                updated_at=excluded.updated_at
            """,
            (concept_slug, mastery, last_tested, test_count, now_iso()),
        )

    def get_progress(self, concept_slug: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM knowledge_progress WHERE concept_slug = ?",
            (concept_slug,),
        ).fetchone()
        return dict(row) if row else None

    def list_progress(self, domain: Optional[str] = None) -> list[dict]:
        """List progress rows, LEFT JOIN knowledge_concepts for title/domain."""
        conn = get_connection()
        sql = (
            "SELECT kp.concept_slug, kp.mastery, kp.last_tested, "
            "kp.test_count, kp.updated_at, kc.title, kc.domain "
            "FROM knowledge_progress kp "
            "LEFT JOIN knowledge_concepts kc ON kp.concept_slug = kc.slug"
        )
        if domain:
            sql += " WHERE kc.domain = ?"
            rows = conn.execute(sql, (domain,)).fetchall()
        else:
            rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]


def _skill_row_to_dict(row) -> dict:
    """Convert a skill_config row to dict, normalising enabled (0/1 → bool)."""
    d = dict(row)
    if "enabled" in d:
        d["enabled"] = bool(d["enabled"])
    return d


# Singleton
knowledge_repo = KnowledgeRepo()

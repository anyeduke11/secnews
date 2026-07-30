"""Security repository — SQLite access for security knowledge graph + terminology.

Tables:
  - security_entities
  - security_edges
  - security_terms
  - security_synonyms
  - security_taxonomy
"""
from __future__ import annotations

import json
from typing import Any, Optional

from backend.domain.security_models import (
    SecurityEdge,
    SecurityEntity,
    SecurityTerm,
    _now_iso,
    _parse_json,
)
from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


VALID_ENTITY_TYPES = (
    "tactic",
    "technique",
    "cve",
    "cwe",
    "compliance",
    "product",
    "cpe",
)

VALID_EDGE_TYPES = (
    "uses",
    "subtechnique-of",
    "mitigates",
    "causes",
    "fixes",
    "requires",
    "related-to",
)

VALID_TERM_TYPES = (
    "cve",
    "cwe",
    "attack_tactic",
    "attack_technique",
    "compliance",
    "product",
    "generic",
)


class SecurityRepository:
    """CRUD + query for security_entities / security_edges / security_terms / synonyms / taxonomy."""

    # ------------------------------------------------------------------
    # security_entities
    # ------------------------------------------------------------------
    def upsert_entity(self, entity: SecurityEntity) -> None:
        conn = get_connection()
        now = entity.updated_at or _now_iso()
        if entity.entity_type not in VALID_ENTITY_TYPES:
            raise InternalException(
                f"entity_type 必须为 {', '.join(VALID_ENTITY_TYPES)}; got {entity.entity_type!r}"
            )
        try:
            conn.execute(
                """
                INSERT INTO security_entities (
                    id, entity_type, name, description, external_ref, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    entity_type=excluded.entity_type,
                    name=excluded.name,
                    description=excluded.description,
                    external_ref=excluded.external_ref,
                    metadata=excluded.metadata,
                    updated_at=excluded.updated_at
                """,
                (
                    entity.id,
                    entity.entity_type,
                    entity.name,
                    entity.description,
                    entity.external_ref,
                    json.dumps(entity.metadata, ensure_ascii=False),
                    entity.created_at or now,
                    now,
                ),
            )
        except Exception as e:
            logger.error("security_entities upsert failed", extra={"error": str(e), "id": entity.id})
            raise InternalException(f"security_entities upsert failed: {e}") from e

    def get_entity(self, entity_id: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM security_entities WHERE id = ?", (entity_id,)
        ).fetchone()
        return SecurityEntity.from_row(dict(row)).to_dict() if row else None

    def list_entities(
        self,
        entity_type: Optional[str] = None,
        name_pattern: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        conn = get_connection()
        where: list[str] = []
        params: list = []
        if entity_type:
            where.append("entity_type = ?")
            params.append(entity_type)
        if name_pattern:
            where.append("name LIKE ?")
            params.append(f"%{name_pattern}%")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM security_entities {where_sql}", params
        ).fetchone()
        total = int(total_row["n"]) if total_row else 0

        rows = conn.execute(
            f"SELECT * FROM security_entities {where_sql} "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, int(limit), int(offset)),
        ).fetchall()
        return [SecurityEntity.from_row(dict(r)).to_dict() for r in rows], total

    def search_entities(self, query: str, entity_types: Optional[list[str]] = None) -> list[dict]:
        conn = get_connection()
        params: list = [f"%{query}%", f"%{query}%"]
        type_filter = ""
        if entity_types:
            placeholders = ",".join("?" for _ in entity_types)
            type_filter = f"AND entity_type IN ({placeholders})"
            params.extend(entity_types)

        rows = conn.execute(
            f"SELECT * FROM security_entities "
            f"WHERE (name LIKE ? OR id LIKE ?) {type_filter} "
            "ORDER BY created_at DESC LIMIT 50",
            params,
        ).fetchall()
        return [SecurityEntity.from_row(dict(r)).to_dict() for r in rows]

    # ------------------------------------------------------------------
    # security_edges
    # ------------------------------------------------------------------
    def upsert_edge(self, edge: SecurityEdge) -> None:
        conn = get_connection()
        now = edge.created_at or _now_iso()
        try:
            conn.execute(
                """
                INSERT INTO security_edges (
                    source_id, target_id, edge_type, weight, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, edge_type) DO UPDATE SET
                    weight=excluded.weight,
                    metadata=excluded.metadata
                """,
                (
                    edge.source_id,
                    edge.target_id,
                    edge.edge_type,
                    edge.weight,
                    json.dumps(edge.metadata, ensure_ascii=False),
                    now,
                ),
            )
        except Exception as e:
            logger.error("security_edges upsert failed", extra={"error": str(e)})
            raise InternalException(f"security_edges upsert failed: {e}") from e

    def get_edges(
        self,
        entity_id: Optional[str] = None,
        edge_type: Optional[str] = None,
    ) -> list[dict]:
        conn = get_connection()
        where: list[str] = []
        params: list = []
        if entity_id:
            where.append("(source_id = ? OR target_id = ?)")
            params.extend([entity_id, entity_id])
        if edge_type:
            where.append("edge_type = ?")
            params.append(edge_type)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        rows = conn.execute(
            f"SELECT * FROM security_edges {where_sql} ORDER BY created_at DESC",
            params,
        ).fetchall()
        return [SecurityEdge.from_row(dict(r)).to_dict() for r in rows]

    def get_related(self, entity_id: str, depth: int = 1) -> dict:
        conn = get_connection()
        seen: set[str] = set()
        nodes: list[dict] = []
        edges: list[dict] = []

        current_ids = {entity_id}
        for _ in range(depth):
            next_ids: set[str] = set()
            rows = conn.execute(
                "SELECT * FROM security_edges WHERE source_id IN ({}) OR target_id IN ({})".format(
                    ",".join("?" for _ in current_ids),
                    ",".join("?" for _ in current_ids),
                ),
                list(current_ids) * 2,
            ).fetchall()
            for row in rows:
                edge = SecurityEdge.from_row(dict(row))
                edges.append(edge.to_dict())
                for nid in (edge.source_id, edge.target_id):
                    if nid not in seen:
                        seen.add(nid)
                        next_ids.add(nid)
            current_ids = next_ids

        for nid in seen:
            entity = self.get_entity(nid)
            if entity:
                nodes.append(entity)

        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # security_terms + synonyms + taxonomy
    # ------------------------------------------------------------------
    def upsert_term(self, term: SecurityTerm) -> SecurityTerm:
        conn = get_connection()
        now = term.updated_at or _now_iso()
        if term.id:
            row = conn.execute(
                "SELECT * FROM security_terms WHERE id = ?", (term.id,)
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE security_terms SET
                        canonical=?, term_type=?, category=?, definition=?,
                        external_id=?, external_ref=?, metadata=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        term.canonical,
                        term.term_type,
                        term.category,
                        term.definition,
                        term.external_id,
                        term.external_ref,
                        json.dumps(term.metadata, ensure_ascii=False),
                        now,
                        term.id,
                    ),
                )
                return term

        cursor = conn.execute(
            """
            INSERT INTO security_terms (
                canonical, term_type, category, definition, external_id, external_ref, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                term.canonical,
                term.term_type,
                term.category,
                term.definition,
                term.external_id,
                term.external_ref,
                json.dumps(term.metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
        term.id = cursor.lastrowid
        return term

    def get_term_by_canonical(self, canonical: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM security_terms WHERE canonical = ?", (canonical,)
        ).fetchone()
        return SecurityTerm.from_row(dict(row)).to_dict() if row else None

    def search_terms(self, query: str, term_type: Optional[str] = None, limit: int = 20) -> list[dict]:
        conn = get_connection()
        params: list = [f"%{query}%"]
        type_filter = ""
        if term_type:
            type_filter = "AND term_type = ?"
            params.append(term_type)
        rows = conn.execute(
            f"SELECT * FROM security_terms WHERE canonical LIKE ? {type_filter} "
            "ORDER BY updated_at DESC LIMIT ?",
            (*params, int(limit)),
        ).fetchall()
        return [SecurityTerm.from_row(dict(r)).to_dict() for r in rows]

    def add_synonym(self, term_id: int, synonym: str, locale: str = "zh-CN") -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO security_synonyms (term_id, synonym, locale, created_at) VALUES (?, ?, ?, ?)",
                (term_id, synonym, locale, _now_iso()),
            )
        except Exception as e:
            logger.error("security_synonyms insert failed", extra={"error": str(e)})
            raise InternalException(f"security_synonyms insert failed: {e}") from e

    def get_synonyms(self, term_id: int) -> list[str]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT synonym FROM security_synonyms WHERE term_id = ? ORDER BY created_at ASC",
            (term_id,),
        ).fetchall()
        return [str(r["synonym"]) for r in rows]

    def get_taxonomy(self, term_type: Optional[str] = None) -> list[dict]:
        conn = get_connection()
        params: list = []
        type_filter = ""
        if term_type:
            type_filter = "AND st.term_type = ?"
            params.append(term_type)
        sql = f"""
            SELECT st.*, parent.term_type AS parent_type
            FROM security_taxonomy t
            JOIN security_terms st ON st.id = t.term_id
            LEFT JOIN security_terms parent ON parent.id = t.parent_id
            WHERE 1=1 {type_filter}
            ORDER BY t.parent_id IS NULL DESC, t.sort_order ASC, st.canonical ASC
        """
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


__all__ = [
    "SecurityRepository",
    "VALID_ENTITY_TYPES",
    "VALID_EDGE_TYPES",
    "VALID_TERM_TYPES",
]

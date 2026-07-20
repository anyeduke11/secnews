"""Phase 2b CodeGarden 联动引擎 — cg_dependencies (依赖图谱) + cg_events (事件总线) CRUD.

设计要点
--------
- cg_dependencies: (source_type, source_id) → (target_type, target_id) 多态引用
  无外键约束, 应用层负责一致性. UNIQUE 约束防重复.
- cg_events: 事件 pending → processed/failed 状态机
- impact_analysis: 递归查询 target_id=X 的所有上游 source (反向追溯)
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


VALID_DEP_TYPES = ("code", "service", "data")
VALID_DEP_ENTITY_TYPES = ("project", "service")

VALID_EVENT_TYPES = (
    "code_push", "service_error", "port_conflict",
    "dep_update", "project_archive",
)
VALID_EVENT_SOURCES = ("project", "service", "resource", "scheduler")
VALID_EVENT_STATUSES = ("pending", "processed", "failed")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _parse_json(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _row_to_dependency(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"]),
        "source_type": str(row["source_type"]),
        "source_id": str(row["source_id"]),
        "target_type": str(row["target_type"]),
        "target_id": str(row["target_id"]),
        "dep_type": str(row["dep_type"]),
        "metadata": _parse_json(row["metadata"], {}),
        "created_at": str(row["created_at"]),
    }


def _row_to_event(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"]),
        "event_type": str(row["event_type"]),
        "source_type": str(row["source_type"]),
        "source_id": str(row["source_id"]),
        "payload": _parse_json(row["payload"], {}),
        "status": str(row["status"]),
        "created_at": str(row["created_at"]),
        "processed_at": row["processed_at"],
        "error_message": row["error_message"],
    }


# ===========================================================================
# Dependency Repository
# ===========================================================================
class CodegardenDependencyRepository:
    """cg_dependencies 表 CRUD + impact_analysis 反向追溯."""

    def create(
        self,
        *,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        dep_type: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        if source_type not in VALID_DEP_ENTITY_TYPES:
            raise InternalException(f"source_type 必须为 {VALID_DEP_ENTITY_TYPES}; got {source_type!r}")
        if target_type not in VALID_DEP_ENTITY_TYPES:
            raise InternalException(f"target_type 必须为 {VALID_DEP_ENTITY_TYPES}; got {target_type!r}")
        if dep_type not in VALID_DEP_TYPES:
            raise InternalException(f"dep_type 必须为 {VALID_DEP_TYPES}; got {dep_type!r}")
        if not source_id or not target_id:
            raise InternalException("source_id 和 target_id 不能为空")

        dep_id = _new_id()
        now = _now_iso()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO cg_dependencies (
                    id, source_type, source_id, target_type, target_id, dep_type, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (dep_id, source_type, source_id, target_type, target_id, dep_type, meta_json, now),
            )
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            if "UNIQUE" in str(e):
                raise InternalException(
                    f"依赖已存在: {source_type}:{source_id} → {target_type}:{target_id} ({dep_type})"
                ) from e
            raise InternalException(f"cg_dependencies create failed: {e}") from e
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"cg_dependencies create failed: {e}") from e

        return self.get(dep_id)  # type: ignore[return-value]

    def get(self, dep_id: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM cg_dependencies WHERE id = ?", (dep_id,)
        ).fetchone()
        return _row_to_dependency(row) if row else None

    def list(
        self,
        *,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        dep_type: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        conn = get_connection()
        where: list[str] = []
        params: list = []
        if source_type:
            where.append("source_type = ?")
            params.append(source_type)
        if source_id:
            where.append("source_id = ?")
            params.append(source_id)
        if target_type:
            where.append("target_type = ?")
            params.append(target_type)
        if target_id:
            where.append("target_id = ?")
            params.append(target_id)
        if dep_type:
            where.append("dep_type = ?")
            params.append(dep_type)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM cg_dependencies {where_sql}", params
        ).fetchone()
        total = int(total_row["n"]) if total_row else 0

        rows = conn.execute(
            f"""
            SELECT * FROM cg_dependencies {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, int(limit), int(offset)),
        ).fetchall()
        return [_row_to_dependency(r) for r in rows], total

    def delete(self, dep_id: str) -> bool:
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                "DELETE FROM cg_dependencies WHERE id = ?", (dep_id,)
            )
            conn.execute("COMMIT")
            return cur.rowcount > 0
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"cg_dependencies delete failed: {e}") from e

    def impact_analysis(
        self,
        *,
        target_type: str,
        target_id: str,
        max_depth: int = 10,
    ) -> list[dict]:
        """反向追溯: 给定 target (X), 找出所有直接/间接依赖 X 的 source.

        算法: BFS, 从 target 出发反向遍历 (谁依赖我 → 谁依赖依赖我的人 → ...).
        Returns: 所有上游 source 列表 (含深度信息).
        """
        if max_depth < 1:
            max_depth = 10

        conn = get_connection()
        visited: set[str] = set()
        result: list[dict] = []
        # 队列: (entity_type, entity_id, depth)
        queue: list[tuple[str, str, int]] = [(target_type, target_id, 0)]

        while queue:
            etype, eid, depth = queue.pop(0)
            key = f"{etype}:{eid}"
            if key in visited or depth >= max_depth:
                continue
            visited.add(key)

            # 找所有 source 依赖当前 entity (target)
            rows = conn.execute(
                """
                SELECT * FROM cg_dependencies
                WHERE target_type = ? AND target_id = ?
                """,
                (etype, eid),
            ).fetchall()
            for r in rows:
                dep = _row_to_dependency(r)
                dep["_depth"] = depth + 1
                result.append(dep)
                src_key = f"{dep['source_type']}:{dep['source_id']}"
                if src_key not in visited:
                    queue.append((dep["source_type"], dep["source_id"], depth + 1))
        return result


# ===========================================================================
# Event Repository
# ===========================================================================
class CodegardenEventRepository:
    """cg_events 表 CRUD + list_pending + mark_processed."""

    def create(
        self,
        *,
        event_type: str,
        source_type: str,
        source_id: str,
        payload: Optional[dict] = None,
        status: str = "pending",
    ) -> dict:
        if event_type not in VALID_EVENT_TYPES:
            raise InternalException(
                f"event_type 必须为 {VALID_EVENT_TYPES}; got {event_type!r}"
            )
        if source_type not in VALID_EVENT_SOURCES:
            raise InternalException(
                f"source_type 必须为 {VALID_EVENT_SOURCES}; got {source_type!r}"
            )
        if status not in VALID_EVENT_STATUSES:
            raise InternalException(f"status 必须为 {VALID_EVENT_STATUSES}; got {status!r}")
        if not source_id:
            raise InternalException("source_id 不能为空")

        event_id = _new_id()
        now = _now_iso()
        payload_json = json.dumps(payload or {}, ensure_ascii=False)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO cg_events (
                    id, event_type, source_type, source_id, payload, status,
                    created_at, processed_at, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (event_id, event_type, source_type, source_id, payload_json, status, now),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error(f"cg_events create failed: {e}")
            raise InternalException(f"cg_events create failed: {e}") from e

        return self.get(event_id)  # type: ignore[return-value]

    def get(self, event_id: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM cg_events WHERE id = ?", (event_id,)
        ).fetchone()
        return _row_to_event(row) if row else None

    def list(
        self,
        *,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        conn = get_connection()
        where: list[str] = []
        params: list = []
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)
        if status:
            where.append("status = ?")
            params.append(status)
        if source_type:
            where.append("source_type = ?")
            params.append(source_type)
        if source_id:
            where.append("source_id = ?")
            params.append(source_id)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM cg_events {where_sql}", params
        ).fetchone()
        total = int(total_row["n"]) if total_row else 0

        rows = conn.execute(
            f"""
            SELECT * FROM cg_events {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, int(limit), int(offset)),
        ).fetchall()
        return [_row_to_event(r) for r in rows], total

    def list_pending(self, limit: int = 50) -> list[dict]:
        """取 pending 状态事件 (按创建时间升序, 旧的先处理)."""
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT * FROM cg_events WHERE status = 'pending'
            ORDER BY created_at ASC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [_row_to_event(r) for r in rows]

    def mark_processed(
        self,
        event_id: str,
        *,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> dict:
        existing = self.get(event_id)
        if existing is None:
            raise InternalException(f"event {event_id} 不存在")

        new_status = "processed" if success else "failed"
        now = _now_iso()
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                UPDATE cg_events
                SET status = ?, processed_at = ?, error_message = ?
                WHERE id = ?
                """,
                (new_status, now, error_message, event_id),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"cg_events mark_processed failed: {e}") from e

        return self.get(event_id)  # type: ignore[return-value]


__all__ = [
    "CodegardenDependencyRepository",
    "CodegardenEventRepository",
    "VALID_DEP_TYPES",
    "VALID_DEP_ENTITY_TYPES",
    "VALID_EVENT_TYPES",
    "VALID_EVENT_SOURCES",
    "VALID_EVENT_STATUSES",
]

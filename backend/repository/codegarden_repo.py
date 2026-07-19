"""Phase 2a CodeGarden 项目仓库 — cg_projects + cg_project_stages +
cg_project_links + cg_project_activities 表 CRUD.

设计要点
--------
- cg_projects.id 用 TEXT UUID (与 knowledge_items.id 一致, 便于跨端同步)
- JSON 字段 (tags / tech_stack / active_skill_ids) 用 TEXT + json.dumps/loads
- 时间戳 ISO 8601 UTC, 与项目其他表一致
- 反向溯源 source_item_id 不加外键约束 (应用层负责一致性)
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


VALID_PROJECT_TYPES = (
    "web_application", "api_service", "cli", "crawler", "library", "experiment",
)
VALID_SOURCE_TYPES = ("vibe", "fork", "imported", "reference")
VALID_LIFECYCLE_STAGES = (
    "ideation", "prototype", "development", "testing",
    "running", "maintenance", "archived", "deprecated",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _parse_json(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


class CodegardenProjectRepository:
    """cg_projects 表 CRUD + 多维筛选 + activities/stages 写入。"""

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def create(
        self,
        *,
        name: str,
        type: str,
        source_type: str,
        lifecycle_stage: str = "ideation",
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        local_path: Optional[str] = None,
        repo_url: Optional[str] = None,
        upstream_url: Optional[str] = None,
        upstream_default_branch: Optional[str] = None,
        source_item_id: Optional[str] = None,
        source_type_detail: Optional[str] = None,
        tags: Optional[list[str]] = None,
        tech_stack: Optional[list[str]] = None,
        domain: Optional[str] = None,
        priority: int = 0,
        active_skill_ids: Optional[list[str]] = None,
    ) -> dict:
        if type not in VALID_PROJECT_TYPES:
            raise InternalException(
                f"type 必须为 {', '.join(VALID_PROJECT_TYPES)}; got {type!r}"
            )
        if source_type not in VALID_SOURCE_TYPES:
            raise InternalException(
                f"source_type 必须为 {', '.join(VALID_SOURCE_TYPES)}; got {source_type!r}"
            )
        if lifecycle_stage not in VALID_LIFECYCLE_STAGES:
            raise InternalException(
                f"lifecycle_stage 必须为 {', '.join(VALID_LIFECYCLE_STAGES)}; got {lifecycle_stage!r}"
            )
        if not name or not name.strip():
            raise InternalException("name 不能为空")

        project_id = _new_id()
        now = _now_iso()
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        tech_stack_json = json.dumps(tech_stack or [], ensure_ascii=False)
        skill_ids_json = json.dumps(active_skill_ids or [], ensure_ascii=False)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO cg_projects (
                    id, name, display_name, description, type, source_type,
                    lifecycle_stage, health_score, local_path, repo_url,
                    upstream_url, upstream_default_branch, commits_behind,
                    commits_ahead, last_synced_at, source_item_id,
                    source_type_detail, tags, tech_stack, domain, priority,
                    active_skill_ids, created_at, last_activity_at, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 0, 0, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    project_id, name.strip(), display_name, description, type,
                    source_type, lifecycle_stage, local_path, repo_url,
                    upstream_url, upstream_default_branch, source_item_id,
                    source_type_detail, tags_json, tech_stack_json, domain,
                    int(priority), skill_ids_json, now, now,
                ),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            logger.error(f"cg_projects create failed: {e}")
            raise InternalException(f"cg_projects create failed: {e}") from e

        return self.get(project_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def get(self, project_id: str) -> Optional[dict]:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM cg_projects WHERE id = ?", (project_id,)
        ).fetchone()
        return _row_to_project(row) if row else None

    def list(
        self,
        *,
        lifecycle_stage: Optional[str] = None,
        source_type: Optional[str] = None,
        domain: Optional[str] = None,
        type: Optional[str] = None,
        source_item_id: Optional[str] = None,
        keyword: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        conn = get_connection()
        where: list[str] = []
        params: list = []
        if lifecycle_stage:
            where.append("lifecycle_stage = ?")
            params.append(lifecycle_stage)
        if source_type:
            where.append("source_type = ?")
            params.append(source_type)
        if domain:
            where.append("domain = ?")
            params.append(domain)
        if type:
            where.append("type = ?")
            params.append(type)
        if source_item_id:
            where.append("source_item_id = ?")
            params.append(source_item_id)
        if not include_archived:
            where.append("lifecycle_stage != 'archived' AND lifecycle_stage != 'deprecated'")
        if keyword:
            kw = keyword.strip()
            if kw:
                where.append("(name LIKE ? OR display_name LIKE ? OR description LIKE ?)")
                like_kw = f"%{kw}%"
                params.extend([like_kw, like_kw, like_kw])
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM cg_projects {where_sql}", params
        ).fetchone()
        total = int(total_row["n"]) if total_row else 0

        rows = conn.execute(
            f"""
            SELECT * FROM cg_projects {where_sql}
            ORDER BY last_activity_at DESC NULLS LAST, created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, int(limit), int(offset)),
        ).fetchall()
        return [_row_to_project(r) for r in rows], total

    # ------------------------------------------------------------------
    # 更新 / 删除 / 状态切换
    # ------------------------------------------------------------------
    def update(self, project_id: str, **fields) -> dict:
        existing = self.get(project_id)
        if existing is None:
            raise InternalException(f"project {project_id} 不存在")

        allowed = {
            "name", "display_name", "description", "type", "source_type",
            "lifecycle_stage", "health_score", "local_path", "repo_url",
            "upstream_url", "upstream_default_branch", "commits_behind",
            "commits_ahead", "last_synced_at", "source_item_id",
            "source_type_detail", "domain", "priority", "archived_at",
        }
        json_fields = {"tags", "tech_stack", "active_skill_ids"}

        sets: list[str] = []
        params: list = []
        for k, v in fields.items():
            if v is None:
                continue
            if k in allowed:
                sets.append(f"{k} = ?")
                params.append(v)
            elif k in json_fields:
                sets.append(f"{k} = ?")
                params.append(json.dumps(v, ensure_ascii=False))
            else:
                raise InternalException(f"不支持更新的字段: {k}")

        if not sets:
            return existing

        sets.append("last_activity_at = ?")
        params.append(_now_iso())
        params.append(project_id)

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                f"UPDATE cg_projects SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"cg_projects update failed: {e}") from e

        return self.get(project_id)  # type: ignore[return-value]

    def set_lifecycle(self, project_id: str, stage: str, note: Optional[str] = None) -> dict:
        if stage not in VALID_LIFECYCLE_STAGES:
            raise InternalException(f"lifecycle_stage 非法: {stage!r}")
        existing = self.get(project_id)
        if existing is None:
            raise InternalException(f"project {project_id} 不存在")
        old_stage = existing["lifecycle_stage"]

        update_fields: dict = {"lifecycle_stage": stage}
        if stage in ("archived", "deprecated"):
            update_fields["archived_at"] = _now_iso()
        updated = self.update(project_id, **update_fields)

        # 写入活动日志
        self.add_activity(
            project_id=project_id,
            activity_type="status_change",
            content=f"lifecycle: {old_stage} → {stage}",
            metadata={"old_stage": old_stage, "new_stage": stage, "note": note},
        )
        return updated

    def delete(self, project_id: str) -> bool:
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                "DELETE FROM cg_projects WHERE id = ?", (project_id,)
            )
            n = int(cur.rowcount)
            conn.execute("COMMIT")
            return n > 0
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"cg_projects delete failed: {e}") from e

    def archive(self, project_id: str) -> dict:
        return self.set_lifecycle(project_id, "archived")

    def restore(self, project_id: str) -> dict:
        existing = self.get(project_id)
        if existing is None:
            raise InternalException(f"project {project_id} 不存在")
        # SQLite 不支持 UPDATE 设 NULL 用 None 通过 update(), 单独处理
        conn = get_connection()
        now = _now_iso()
        try:
            conn.execute("BEGIN")
            conn.execute(
                "UPDATE cg_projects SET lifecycle_stage='maintenance', archived_at=NULL, last_activity_at=? WHERE id=?",
                (now, project_id),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"restore failed: {e}") from e
        self.add_activity(
            project_id=project_id,
            activity_type="status_change",
            content="restore from archived → maintenance",
        )
        return self.get(project_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Activities
    # ------------------------------------------------------------------
    def add_activity(
        self,
        *,
        project_id: str,
        activity_type: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        activity_id = _new_id()
        now = _now_iso()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO cg_project_activities
                (id, project_id, activity_type, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (activity_id, project_id, activity_type, content, meta_json, now),
            )
            conn.execute(
                "UPDATE cg_projects SET last_activity_at = ? WHERE id = ?",
                (now, project_id),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"add_activity failed: {e}") from e
        return {
            "id": activity_id,
            "project_id": project_id,
            "activity_type": activity_type,
            "content": content,
            "metadata": metadata or {},
            "created_at": now,
        }

    def list_activities(self, project_id: str, limit: int = 50) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT * FROM cg_project_activities
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_id, int(limit)),
        ).fetchall()
        return [_row_to_activity(r) for r in rows]

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------
    def list_stages(self, project_id: str) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM cg_project_stages WHERE project_id = ? ORDER BY stage_order",
            (project_id,),
        ).fetchall()
        return [_row_to_stage(r) for r in rows]

    def add_stage(
        self,
        *,
        project_id: str,
        stage_name: str,
        stage_order: Optional[int] = None,
        deliverable_type: Optional[str] = None,
        deliverable_url: Optional[str] = None,
        deliverable_path: Optional[str] = None,
        commit_sha: Optional[str] = None,
        status: str = "planned",
        notes: Optional[str] = None,
    ) -> dict:
        stage_id = _new_id()
        now = _now_iso()
        conn = get_connection()
        if stage_order is None:
            existing = conn.execute(
                "SELECT COALESCE(MAX(stage_order), 0) + 1 AS next_order "
                "FROM cg_project_stages WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            stage_order = int(existing["next_order"]) if existing else 1
        try:
            conn.execute("BEGIN")
            conn.execute(
                """
                INSERT INTO cg_project_stages
                (id, project_id, stage_name, stage_order, deliverable_type,
                 deliverable_url, deliverable_path, commit_sha, status, notes,
                 created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (stage_id, project_id, stage_name, stage_order,
                 deliverable_type, deliverable_url, deliverable_path,
                 commit_sha, status, notes, now),
            )
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"add_stage failed: {e}") from e
        return {
            "id": stage_id, "project_id": project_id,
            "stage_name": stage_name, "stage_order": stage_order,
            "deliverable_type": deliverable_type,
            "deliverable_url": deliverable_url,
            "deliverable_path": deliverable_path,
            "commit_sha": commit_sha, "status": status,
            "notes": notes, "created_at": now, "completed_at": None,
        }


# ---------------------------------------------------------------------------
# Row → dict helpers
# ---------------------------------------------------------------------------
def _row_to_project(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "display_name": row["display_name"],
        "description": row["description"],
        "type": str(row["type"]),
        "source_type": str(row["source_type"]),
        "lifecycle_stage": str(row["lifecycle_stage"]),
        "health_score": int(row["health_score"] or 0),
        "local_path": row["local_path"],
        "repo_url": row["repo_url"],
        "upstream_url": row["upstream_url"],
        "upstream_default_branch": row["upstream_default_branch"],
        "commits_behind": int(row["commits_behind"] or 0),
        "commits_ahead": int(row["commits_ahead"] or 0),
        "last_synced_at": row["last_synced_at"],
        "source_item_id": row["source_item_id"],
        "source_type_detail": row["source_type_detail"],
        "tags": _parse_json(row["tags"], []),
        "tech_stack": _parse_json(row["tech_stack"], []),
        "domain": row["domain"],
        "priority": int(row["priority"] or 0),
        "active_skill_ids": _parse_json(row["active_skill_ids"], []),
        "created_at": str(row["created_at"]),
        "last_activity_at": row["last_activity_at"],
        "archived_at": row["archived_at"],
    }


def _row_to_activity(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "activity_type": str(row["activity_type"]),
        "content": str(row["content"]),
        "metadata": _parse_json(row["metadata"], {}),
        "created_at": str(row["created_at"]),
    }


def _row_to_stage(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "stage_name": str(row["stage_name"]),
        "stage_order": int(row["stage_order"]),
        "deliverable_type": row["deliverable_type"],
        "deliverable_url": row["deliverable_url"],
        "deliverable_path": row["deliverable_path"],
        "commit_sha": row["commit_sha"],
        "status": str(row["status"]),
        "notes": row["notes"],
        "created_at": str(row["created_at"]),
        "completed_at": row["completed_at"],
    }


__all__ = [
    "CodegardenProjectRepository",
    "VALID_PROJECT_TYPES",
    "VALID_SOURCE_TYPES",
    "VALID_LIFECYCLE_STAGES",
]

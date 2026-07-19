"""Phase 2a CodeGarden 项目服务层 — 封装 repo + 业务规则.

职责
----
- 项目 CRUD（委托 repo）
- lifecycle 状态机校验（合法跳转）
- activities 写入
- upstream sync 触发（写 knowledge_tasks 记录，不直接调 GitHub API）
"""
from __future__ import annotations

from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.codegarden_repo import CodegardenProjectRepository
from backend.repository.db import get_connection


# lifecycle 合法跳转表（from → set of to）
_LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "ideation": {"prototype", "development", "archived", "deprecated"},
    "prototype": {"development", "testing", "archived", "deprecated"},
    "development": {"testing", "running", "archived", "deprecated"},
    "testing": {"running", "development", "archived", "deprecated"},
    "running": {"maintenance", "archived", "deprecated"},
    "maintenance": {"running", "archived", "deprecated"},
    "archived": {"maintenance"},  # restore
    "deprecated": {"archived"},
}


class CodegardenProjectService:
    """项目业务逻辑层。"""

    def __init__(self) -> None:
        self.repo = CodegardenProjectRepository()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_project(self, **kwargs) -> dict:
        project = self.repo.create(**kwargs)
        self.repo.add_activity(
            project_id=project["id"],
            activity_type="note",
            content=f"项目创建: type={project['type']}, source={project['source_type']}",
            metadata={"created": True},
        )
        return project

    def get_project(self, project_id: str) -> Optional[dict]:
        return self.repo.get(project_id)

    def list_projects(self, **filters) -> tuple[list[dict], int]:
        return self.repo.list(**filters)

    def update_project(self, project_id: str, **fields) -> dict:
        return self.repo.update(project_id, **fields)

    def delete_project(self, project_id: str) -> bool:
        return self.repo.delete(project_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def change_lifecycle(self, project_id: str, new_stage: str, note: Optional[str] = None) -> dict:
        project = self.repo.get(project_id)
        if project is None:
            raise InternalException(f"project {project_id} 不存在")
        old_stage = project["lifecycle_stage"]
        if old_stage == new_stage:
            return project
        legal_targets = _LEGAL_TRANSITIONS.get(old_stage, set())
        if new_stage not in legal_targets:
            raise InternalException(
                f"非法 lifecycle 跳转: {old_stage} → {new_stage} "
                f"(合法目标: {sorted(legal_targets) or '无'})"
            )
        return self.repo.set_lifecycle(project_id, new_stage, note)

    def archive_project(self, project_id: str) -> dict:
        return self.change_lifecycle(project_id, "archived", note="归档")

    def restore_project(self, project_id: str) -> dict:
        return self.repo.restore(project_id)

    # ------------------------------------------------------------------
    # Activities
    # ------------------------------------------------------------------
    def add_activity(self, *, project_id: str, activity_type: str, content: str,
                     metadata: Optional[dict] = None) -> dict:
        return self.repo.add_activity(
            project_id=project_id,
            activity_type=activity_type,
            content=content,
            metadata=metadata,
        )

    def list_activities(self, project_id: str, limit: int = 50) -> list[dict]:
        return self.repo.list_activities(project_id, limit)

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------
    def list_stages(self, project_id: str) -> list[dict]:
        return self.repo.list_stages(project_id)

    def add_stage(self, **kwargs) -> dict:
        return self.repo.add_stage(**kwargs)

    # ------------------------------------------------------------------
    # Upstream sync 任务创建
    # ------------------------------------------------------------------
    def request_upstream_sync(self, project_id: str) -> dict:
        """创建上游同步任务（写入 knowledge_tasks 表, task_type=project_sync）.

        实际同步由 watchdog 或手动触发执行，避免 HTTP 阻塞。
        """
        from datetime import datetime, timezone
        import json

        project = self.repo.get(project_id)
        if project is None:
            raise InternalException(f"project {project_id} 不存在")
        if not project.get("upstream_url") and not project.get("repo_url"):
            raise InternalException("项目无 upstream_url / repo_url, 无法同步")

        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO knowledge_tasks (task_type, status, params, created_at, updated_at)
                VALUES (?, 'pending', ?, ?, ?)
                """,
                ("project_sync", json.dumps({"project_id": project_id}), now, now),
            )
            task_id = int(cur.lastrowid)
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"create sync task failed: {e}") from e

        logger.info(f"created project_sync task {task_id} for project {project_id}")
        return {"task_id": task_id, "project_id": project_id, "status": "pending"}


__all__ = ["CodegardenProjectService"]

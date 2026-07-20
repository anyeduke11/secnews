"""Phase 2b CodeGarden 联动引擎业务层.

职责
----
- 依赖图谱 CRUD + impact_analysis (委托 repo)
- 事件总线: publish_event (写 cg_events + 创建 knowledge_tasks event_handler)
- Playbook: list_playbooks (扫 codegarden/playbooks/*.yml) + run_playbook (创建 playbook_run task)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.codegarden_orchestration_repo import (
    CodegardenDependencyRepository,
    CodegardenEventRepository,
)
from backend.repository.db import get_connection


# Playbook YAML 文件目录 (相对项目根)
PLAYBOOKS_DIR = Path("codegarden/playbooks")


class CodegardenOrchestrationService:
    """联动引擎业务逻辑层."""

    def __init__(self) -> None:
        self.dep_repo = CodegardenDependencyRepository()
        self.event_repo = CodegardenEventRepository()

    # ------------------------------------------------------------------
    # Dependencies CRUD
    # ------------------------------------------------------------------
    def create_dependency(self, **kwargs) -> dict:
        return self.dep_repo.create(**kwargs)

    def list_dependencies(self, **filters) -> tuple[list[dict], int]:
        return self.dep_repo.list(**filters)

    def delete_dependency(self, dep_id: str) -> bool:
        return self.dep_repo.delete(dep_id)

    def impact_analysis(
        self, *, target_type: str, target_id: str, max_depth: int = 10
    ) -> list[dict]:
        return self.dep_repo.impact_analysis(
            target_type=target_type, target_id=target_id, max_depth=max_depth
        )

    # ------------------------------------------------------------------
    # Events — 发布 + 查询
    # ------------------------------------------------------------------
    def list_events(self, **filters) -> tuple[list[dict], int]:
        return self.event_repo.list(**filters)

    def list_pending_events(self, limit: int = 50) -> list[dict]:
        return self.event_repo.list_pending(limit)

    def publish_event(
        self,
        *,
        event_type: str,
        source_type: str,
        source_id: str,
        payload: Optional[dict] = None,
    ) -> dict:
        """发布事件 + 创建处理 task (异步处理).

        1. 写入 cg_events (status=pending)
        2. 创建 knowledge_tasks (task_type=event_handler, params={event_id})
        3. 实际处理由 cg_event_process job (60s) 异步执行

        Returns: {"event": {...}, "task_id": int}
        """
        event = self.event_repo.create(
            event_type=event_type,
            source_type=source_type,
            source_id=source_id,
            payload=payload,
        )

        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO knowledge_tasks (task_type, status, params, created_at, updated_at)
                VALUES (?, 'pending', ?, ?, ?)
                """,
                (
                    "event_handler",
                    json.dumps({"event_id": event["id"]}),
                    now, now,
                ),
            )
            task_id = int(cur.lastrowid)
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            # 不抛异常, 事件已写入, task 失败由 cg_event_process 兜底扫描 pending 事件
            logger.warning(
                f"publish_event: create event_handler task failed (event_id={event['id']}): {e}"
            )
            return {"event": event, "task_id": None}

        logger.info(
            f"publish_event: event_id={event['id']} task_id={task_id} type={event_type}"
        )
        return {"event": event, "task_id": task_id}

    def mark_event_processed(
        self,
        event_id: str,
        *,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> dict:
        return self.event_repo.mark_processed(
            event_id, success=success, error_message=error_message
        )

    # ------------------------------------------------------------------
    # Playbook — list + run
    # ------------------------------------------------------------------
    def list_playbooks(self) -> list[dict]:
        """扫描 codegarden/playbooks/*.yml, 返回 [{name, path, content}]."""
        playbooks: list[dict] = []
        if not PLAYBOOKS_DIR.exists():
            return playbooks

        for pb_file in sorted(PLAYBOOKS_DIR.glob("*.yml")):
            try:
                content = pb_file.read_text(encoding="utf-8")
                playbooks.append({
                    "name": pb_file.stem,
                    "path": str(pb_file),
                    "content": content,
                    "size": len(content),
                })
            except Exception as e:
                logger.warning(f"list_playbooks: read {pb_file} failed: {e}")
        return playbooks

    def get_playbook(self, name: str) -> dict:
        """获取单个 Playbook 详情 (含解析后的 steps)."""
        pb_path = PLAYBOOKS_DIR / f"{name}.yml"
        if not pb_path.exists():
            raise InternalException(f"Playbook {name!r} 不存在")

        content = pb_path.read_text(encoding="utf-8")
        try:
            import yaml
            parsed = yaml.safe_load(content) or {}
        except ImportError:
            # PyYAML 未安装, 返回原始内容
            parsed = {}
        except Exception as e:
            raise InternalException(f"Playbook {name!r} YAML 解析失败: {e}") from e

        return {
            "name": name,
            "path": str(pb_path),
            "content": content,
            "parsed": parsed,
            "steps": parsed.get("steps", []) if isinstance(parsed, dict) else [],
        }

    def run_playbook(self, name: str, params: Optional[dict] = None) -> dict:
        """执行 Playbook — 创建 knowledge_tasks (task_type=playbook_run).

        实际执行由 watchdog 或 Agent 异步处理 (与本系统其他 task 一致).
        Returns: {"task_id": int, "playbook_name": str, "status": "pending"}
        """
        pb = self.get_playbook(name)  # 含存在性校验

        now = datetime.now(timezone.utc).isoformat()
        task_params = {
            "playbook_name": name,
            "playbook_path": pb["path"],
            "steps": pb["steps"],
            "user_params": params or {},
        }

        conn = get_connection()
        try:
            conn.execute("BEGIN")
            cur = conn.execute(
                """
                INSERT INTO knowledge_tasks (task_type, status, params, created_at, updated_at)
                VALUES (?, 'pending', ?, ?, ?)
                """,
                ("playbook_run", json.dumps(task_params, ensure_ascii=False), now, now),
            )
            task_id = int(cur.lastrowid)
            conn.execute("COMMIT")
        except Exception as e:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise InternalException(f"create playbook_run task failed: {e}") from e

        logger.info(
            f"run_playbook: name={name} task_id={task_id} steps_count={len(pb['steps'])}"
        )
        return {
            "task_id": task_id,
            "playbook_name": name,
            "status": "pending",
            "steps_count": len(pb["steps"]),
        }


__all__ = ["CodegardenOrchestrationService", "PLAYBOOKS_DIR"]

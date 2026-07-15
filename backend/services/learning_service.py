"""Learning plan service — CRUD for weekly learning plans + generate task.

Design: backend handles plan storage (SQLite) and task creation.
The actual LLM-based plan generation is done by Agent via knowledge-master
skill, triggered by a task file in knowledge/learning/tasks/pending/.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

from backend.domain.knowledge_models import now_iso
from backend.repository.knowledge_repo import knowledge_repo

log = logging.getLogger("hotspot.learning")

PENDING_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge"
    / "learning"
    / "tasks"
    / "pending"
)


def _current_iso_week() -> str:
    """Return current ISO week string, e.g. '2026-W29'."""
    iso = date.today().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def list_plans(status: Optional[str] = None) -> list[dict]:
    """List all learning plans, optionally filtered by status."""
    return knowledge_repo.list_plans(status=status)


def get_plan(week: str) -> Optional[dict]:
    """Get a single learning plan by week (e.g. '2026-W29')."""
    return knowledge_repo.get_plan(week)


def create_plan(
    week: str,
    goals: list[str],
    task_item_ids: list[str],
) -> dict:
    """Create or replace a weekly learning plan.

    plan_data shape: {goals: [...], tasks: [{item_id, title, completed}]}
    """
    tasks = []
    for item_id in task_item_ids:
        item = knowledge_repo.get_item(item_id)
        tasks.append({
            "item_id": item_id,
            "title": item.title if item else item_id,
            "completed": False,
        })

    plan_data = {"goals": goals, "tasks": tasks}
    record = {
        "week": week,
        "status": "active",
        "plan_data": plan_data,
        "created_at": now_iso(),
    }
    knowledge_repo.upsert_plan(record)
    log.info(f"upserted learning plan for {week}: {len(tasks)} tasks")
    return knowledge_repo.get_plan(week)


def update_plan_status(week: str, status: str) -> dict:
    """Update the status of a learning plan (active/completed/archived)."""
    knowledge_repo.update_plan_status(week, status)
    log.info(f"updated plan {week} status -> {status}")
    return knowledge_repo.get_plan(week)


def generate_plan_task(domains: Optional[list[str]] = None) -> dict:
    """Create a generate_learning_plan task for Agent to execute.

    Writes a task file to knowledge/learning/tasks/pending/ for the Agent
    to pick up via the knowledge-master skill.
    """
    week = _current_iso_week()
    params = {"domains": domains or [], "week": week}
    task = knowledge_repo.create_task("generate_learning_plan", params)

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    task_path = PENDING_DIR / f"task-{task.id}.md"
    task_path.write_text(
        f"""---
task_id: {task.id}
task_type: generate_learning_plan
status: pending
created_at: "{now_iso()}"
params:
  domains: {domains or []}
  week: "{week}"
---

# 任务：生成学习计划

请使用 knowledge-master skill 为本周（{week}）生成学习计划。

## 参数
- 周次: {week}
- 领域: {', '.join(domains) if domains else '全部领域'}

## 步骤
1. 扫描 knowledge/items/ 和 knowledge/concepts/ 了解当前知识状态
2. 根据 SOUL.md 和知识覆盖度，生成本周学习目标（3-5 个）
3. 选择 5-10 个知识条目作为本周学习任务
4. 写入 knowledge_plans 表（通过 API 或直接操作）
""",
        encoding="utf-8",
    )
    log.info(f"created generate_learning_plan task {task.id} for {week}")
    return {"task_id": task.id, "status": "pending", "week": week}

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
from backend.services.knowledge_sync import KNOWLEDGE_DIR

log = logging.getLogger("hotspot.learning")

PENDING_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge"
    / "learning"
    / "tasks"
    / "pending"
)

# Plans .md dual-write directory (Markdown is the truth source per design §3.5).
PLANS_DIR = KNOWLEDGE_DIR / "learning"


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


def _write_plan_md(week: str, plan_data: dict) -> None:
    """Write a learning plan to knowledge/learning/plan-{week}.md.

    Dual-write: SQLite is the queryable store, the .md file is the
    human-readable truth source (design §3.5). Called after
    ``upsert_plan`` / ``update_plan_status``.

    ``plan_data`` is the full plan record (as returned by
    ``knowledge_repo.get_plan``): ``{week, status, plan_data: {goals,
    tasks}, created_at, ...}``. Field-name tolerant: tasks may use either
    ``description``/``done`` (spec §3.5 shape) or ``title``/``completed``
    (current ``create_plan`` shape).
    """
    inner = plan_data.get("plan_data") or {}
    if not isinstance(inner, dict):
        inner = {}
    goals = inner.get("goals") or plan_data.get("goals") or []
    tasks = inner.get("tasks") or plan_data.get("tasks") or []
    status = plan_data.get("status", "active")
    created_at = plan_data.get("created_at", "")
    updated_at = plan_data.get("updated_at") or created_at

    goals_lines = "\n".join(f"- {g}" for g in goals) or "- (无目标)"
    task_lines: list[str] = []
    for t in tasks:
        desc = (
            t.get("description")
            or t.get("title")
            or t.get("item_id")
            or "未命名任务"
        )
        done = t.get("done", t.get("completed", False))
        mark = "x" if done else " "
        task_lines.append(f"- [{mark}] {desc}")
    tasks_md = "\n".join(task_lines) or "- (无任务)"

    content = (
        "---\n"
        f'week: "{week}"\n'
        f'status: "{status}"\n'
        f'created_at: "{created_at}"\n'
        f'updated_at: "{updated_at}"\n'
        "---\n\n"
        f"# 学习计划 {week}\n\n"
        "## 目标\n"
        f"{goals_lines}\n\n"
        "## 任务清单\n"
        f"{tasks_md}\n"
    )
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    path = PLANS_DIR / f"plan-{week}.md"
    path.write_text(content, encoding="utf-8")
    log.info(f"wrote plan md: {path}")


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
    saved = knowledge_repo.get_plan(week)
    _write_plan_md(week, saved or record)
    log.info(f"upserted learning plan for {week}: {len(tasks)} tasks")
    return saved


def update_plan_status(week: str, status: str) -> dict:
    """Update the status of a learning plan (active/completed/archived)."""
    knowledge_repo.update_plan_status(week, status)
    saved = knowledge_repo.get_plan(week)
    if saved:
        saved["status"] = status
        saved["updated_at"] = now_iso()
        _write_plan_md(week, saved)
    log.info(f"updated plan {week} status -> {status}")
    return saved


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

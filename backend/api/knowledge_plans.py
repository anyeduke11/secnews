"""Knowledge API — weekly learning plans + mastery progress + summaries.

拆自 ``backend/api/knowledge.py`` (Batch 2 任务 A): handler 逻辑原样搬移,
路径相对聚合层 (聚合层带 ``/api/knowledge`` prefix), URL 逐字不变。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.repository.knowledge_repo import knowledge_repo

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ── Learning Plans ─────────────────────────────────────────────

@router.get("/plans")
async def list_plans(status: str | None = Query(None)):
    """List weekly learning plans, optionally filtered by status."""
    from backend.services.learning_service import list_plans as svc_list_plans
    return {"plans": svc_list_plans(status=status)}


@router.post("/plans")
async def create_plan(data: dict):
    """Manually create a weekly learning plan."""
    from backend.services.learning_service import create_plan as svc_create_plan
    week = data.get("week")
    if not week:
        raise HTTPException(status_code=400, detail="week is required")
    goals = data.get("goals", [])
    task_item_ids = data.get("task_item_ids", [])
    return svc_create_plan(week=week, goals=goals, task_item_ids=task_item_ids)


@router.post("/plans/generate")
async def generate_plan(data: dict):
    """Generate a learning plan directly by scanning knowledge items."""
    from backend.services.learning_service import generate_plan_direct
    domains = data.get("domains")
    return generate_plan_direct(domains=domains)


@router.get("/plans/{week}")
async def get_plan(week: str):
    """Get a single learning plan by week (e.g. '2026-W29')."""
    from backend.services.learning_service import get_plan as svc_get_plan
    plan = svc_get_plan(week)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.patch("/plans/{week}")
async def update_plan(week: str, data: dict):
    """Update plan status or task completions.

    Body: {status?: str, task_completions?: {item_id: bool}}
    """
    from backend.services.learning_service import update_plan_status
    plan = knowledge_repo.get_plan(week)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    if "status" in data:
        return update_plan_status(week=week, status=data["status"])

    if "task_completions" in data:
        completions = data["task_completions"]
        plan_data = plan["plan_data"]
        for task in plan_data.get("tasks", []):
            if task["item_id"] in completions:
                task["completed"] = completions[task["item_id"]]
        knowledge_repo.upsert_plan({
            "week": week,
            "status": plan["status"],
            "plan_data": plan_data,
            "created_at": plan["created_at"],
        })
        return knowledge_repo.get_plan(week)

    return plan


# ── Learning Progress ──────────────────────────────────────────

@router.get("/progress")
async def list_progress(domain: str | None = Query(None)):
    """List mastery progress for concepts, optionally filtered by domain."""
    from backend.services.progress_service import list_progress as svc_list_progress
    return {"progress": svc_list_progress(domain=domain)}


@router.post("/progress/sync")
async def sync_progress():
    """Manually trigger .json ↔ SQLite sync for progress data."""
    from backend.services.progress_service import sync_progress_from_md, write_progress_to_md
    synced = sync_progress_from_md()
    written = write_progress_to_md()
    return {"synced_from_json": synced["synced"], "written_to_json": written["written"]}


@router.get("/progress/{concept_slug}")
async def get_progress(concept_slug: str):
    """Get mastery progress for a single concept."""
    from backend.services.progress_service import get_progress as svc_get_progress
    progress = svc_get_progress(concept_slug)
    if progress is None:
        raise HTTPException(status_code=404, detail="Progress not found")
    return progress


@router.patch("/progress/{concept_slug}")
async def update_progress(concept_slug: str, data: dict):
    """Update mastery progress.

    Body: {mastery?: int, tested?: bool}
    """
    from backend.services.progress_service import upsert_progress as svc_upsert_progress
    if "mastery" in data:
        mastery = data["mastery"]
    else:
        existing = knowledge_repo.get_progress(concept_slug)
        mastery = existing["mastery"] if existing else 0
    tested = data.get("tested", False)
    return svc_upsert_progress(concept_slug=concept_slug, mastery=mastery, tested=tested)


# ── Phase 1j Task 10.8: Weekly summaries ────────────────────────

@router.get("/summaries")
async def list_summaries():
    """List all weekly summary files (year_week DESC)."""
    from backend.services.summary_service import list_summaries as svc_list_summaries
    return {"summaries": svc_list_summaries()}


@router.post("/summaries/weekly")
async def generate_weekly_summary(data: dict | None = None):
    """Generate the weekly summary markdown for a given ISO week.

    Body: {year_week?: "YYYY-Www"} — defaults to current ISO week.
    """
    from backend.services.summary_service import generate_weekly_summary as svc_gen
    year_week = (data or {}).get("year_week")
    try:
        return svc_gen(year_week)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

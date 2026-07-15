"""Knowledge API — CRUD for knowledge items, concepts, tasks, sync, health."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.domain.knowledge_models import KnowledgeItem, KnowledgeConcept, KnowledgeTask, now_iso
from backend.repository.knowledge_repo import knowledge_repo
from backend.services.cubox_sync import sync_cubox_to_knowledge
from backend.services.knowledge_sync import (
    full_sync_items_to_db,
    full_sync_concepts_to_db,
    write_item_to_md,
)

log = logging.getLogger("hotspot.api.knowledge")
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ── Items ───────────────────────────────────────────────────────

@router.get("/items")
async def list_items(
    domain: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    compiled: Optional[bool] = Query(None),
    topic: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List knowledge items with optional filters."""
    items = knowledge_repo.list_items(
        domain=domain, source=source, compiled=compiled,
        topic=topic, item_type=type, difficulty=difficulty,
        since=since, until=until,
        limit=limit, offset=offset,
    )
    total = knowledge_repo.count_items(domain=domain)
    return {"items": [i.to_dict() for i in items], "total": total}


@router.get("/topics")
async def list_topics(domain: Optional[str] = Query(None)):
    """List distinct topics for filter dropdown."""
    return {"topics": knowledge_repo.list_topics(domain=domain)}


@router.get("/items/{item_id}")
async def get_item(item_id: str):
    """Get a single knowledge item by ID, with markdown content."""
    item = knowledge_repo.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    from pathlib import Path
    md_path = Path(__file__).resolve().parent.parent.parent / "knowledge" / "items" / f"{item_id}.md"
    content = ""
    if md_path.exists():
        text = md_path.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            content = parts[2].strip() if len(parts) >= 3 else text
        else:
            content = text
    result = item.to_dict()
    result["content"] = content
    return result


@router.patch("/items/{item_id}")
async def update_item(item_id: str, data: dict):
    """Update knowledge item fields (classification, tags, mastery)."""
    item = knowledge_repo.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    updatable = ["domain", "topic", "type", "difficulty", "tags", "concepts", "mastered"]
    for key in updatable:
        if key in data:
            setattr(item, key, data[key])

    item.updated_at = now_iso()
    knowledge_repo.upsert_item(item)
    # 写回 .md 文件（注意 to_dict() 的字段名是 mastered，但 write_item_to_md 期望 mastery）
    item_dict = item.to_dict()
    # write_item_to_md 期望 'mastery' 字段名（与 SQL 列一致），但 to_dict 输出 'mastered'
    # 这里做一次字段名转换
    item_dict["mastery"] = item_dict.pop("mastered")
    write_item_to_md(item_dict)
    return item.to_dict()


@router.delete("/items/{item_id}")
async def delete_item(item_id: str):
    """Delete a knowledge item."""
    item = knowledge_repo.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    knowledge_repo.delete_item(item_id)
    # Also delete the .md file
    from pathlib import Path
    md_path = Path(__file__).resolve().parent.parent.parent / "knowledge" / "items" / f"{item_id}.md"
    if md_path.exists():
        md_path.unlink()
    return {"deleted": item_id}


# ── Concepts ────────────────────────────────────────────────────

@router.get("/concepts")
async def list_concepts(domain: Optional[str] = Query(None)):
    """List knowledge concepts."""
    concepts = knowledge_repo.list_concepts(domain=domain)
    return {"concepts": [c.to_dict() for c in concepts]}


@router.get("/concepts/{slug}")
async def get_concept(slug: str):
    """Get concept detail with related items."""
    concept = knowledge_repo.get_concept(slug)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    items = []
    for item_id in concept.source_items:
        item = knowledge_repo.get_item(item_id)
        if item is not None:
            items.append({"id": item.id, "title": item.title, "domain": item.domain})
    result = concept.to_dict()
    result["items"] = items
    return result


# ── Graph ───────────────────────────────────────────────────────

@router.get("/graph")
async def get_graph(
    domain: Optional[str] = Query(None),
    include_local: bool = Query(True),
):
    """Get knowledge graph data (nodes + edges).

    Args:
        domain: optional domain filter
        include_local: merge local wiki nodes (default True)
    """
    from backend.services.graph_builder import build_graph
    return build_graph(domain=domain, include_local=include_local)


# ── Federation ──────────────────────────────────────────────────

@router.get("/federation")
async def get_federation():
    """Get local wiki federation status."""
    from backend.services.federation_service import get_federation_status
    return get_federation_status()


# ── Sync ────────────────────────────────────────────────────────

@router.post("/sync")
async def trigger_sync(source: str = Query("cubox")):
    """Trigger knowledge sync from data sources."""
    results = {"cubox": 0}
    if source in ("cubox", "all"):
        results["cubox"] = sync_cubox_to_knowledge(limit=100)
    # Full sync .md -> SQLite
    results["items_synced"] = full_sync_items_to_db()
    results["concepts_synced"] = full_sync_concepts_to_db()
    return results


# ── Tasks ───────────────────────────────────────────────────────

@router.post("/tasks")
async def create_task(data: dict):
    """Submit a task (e.g. generate_learning_plan)."""
    task_type = data.get("task_type", "unknown")
    params = data.get("params")
    task = knowledge_repo.create_task(task_type, params)
    return task.to_dict()


@router.get("/tasks")
async def list_tasks(status: Optional[str] = Query(None)):
    """List knowledge tasks."""
    tasks = knowledge_repo.list_tasks(status=status)
    return {"tasks": [t.to_dict() for t in tasks]}


# ── Health ──────────────────────────────────────────────────────

@router.get("/health")
async def knowledge_health():
    """Get knowledge wiki health metrics."""
    total = knowledge_repo.count_items()
    compiled_count = knowledge_repo.count_items(compiled=True)
    coverage = knowledge_repo.domain_coverage()
    gap_analysis = [
        {
            "domain": c["domain"],
            "coverage": round(c["coverage"], 2),
            "suggestion": (
                "覆盖良好" if c["coverage"] >= 0.5
                else f"建议补充 {c['domain']} 相关条目"
            ),
        }
        for c in coverage
    ]
    return {
        "total_items": total,
        "total_concepts": len(knowledge_repo.list_concepts()),
        "compiled_count": compiled_count,
        "compiled_ratio": (compiled_count / total) if total > 0 else 0,
        "orphan_items": knowledge_repo.count_orphan_items(),
        "stale_concepts": knowledge_repo.count_stale_concepts(),
        "gap_analysis": gap_analysis,
    }


# ── Bookmarks Import ────────────────────────────────────────────

@router.post("/bookmarks/import")
async def import_bookmarks(data: dict, validate: bool = Query(False)):
    """Import Chrome/Edge bookmarks JSON into knowledge base."""
    from backend.services.bookmark_sync import parse_chrome_bookmarks, import_bookmarks as do_import
    bookmarks = data.get("bookmarks", data)
    items = parse_chrome_bookmarks(bookmarks)
    result = do_import(items, validate=validate)
    return result


# ── History Import ──────────────────────────────────────────────

@router.post("/import-from-history")
async def import_from_history(data: dict):
    """Import archived hotspot items into knowledge base.

    item_ids 是 hotspots 表的 TEXT 主键 (如 "ai_量子位_0").
    """
    from backend.services.history_import import import_from_history as do_import
    item_ids = data.get("item_ids", [])
    return do_import(item_ids)


# ── SOUL.md ─────────────────────────────────────────────────────

@router.get("/soul")
async def get_soul():
    """Get SOUL.md role profile content."""
    from backend.services.soul_service import get_soul
    return get_soul()

@router.post("/soul/regenerate")
async def regenerate_soul():
    """Trigger SOUL.md regeneration (creates task for Agent)."""
    from backend.services.soul_service import create_soul_task
    return create_soul_task()


# ── Compile ─────────────────────────────────────────────────────

@router.get("/compile/preview")
async def compile_preview():
    """Preview items that need recompilation (stale items)."""
    from backend.services.compiler import detect_stale_items
    result = detect_stale_items()
    return {
        "stale_items": result["stale_items"],
        "count": len(result["stale_items"]),
        "reasons": result["reasons"],
    }


@router.post("/compile")
async def compile_items(data: dict):
    """Trigger knowledge compilation (creates task for Agent)."""
    from backend.services.compiler import create_compile_task
    item_ids = data.get("item_ids")
    return create_compile_task(item_ids)


# ── Skills ──────────────────────────────────────────────────────

@router.get("/skills/{skill_name}/validate")
async def validate_skill(skill_name: str):
    """Validate that a skill is ready for publishing (exists, enabled, secret bound)."""
    from backend.services.skill_config_service import validate_skill_for_publish
    return validate_skill_for_publish(skill_name)


@router.get("/skills")
async def list_skills(enabled: Optional[bool] = Query(None)):
    """List skill configs (auto-seeds 13 presets on first call)."""
    from backend.services.skill_config_service import list_skills as _list_skills
    return {"skills": _list_skills(enabled)}


@router.post("/skills")
async def create_skill(data: dict):
    """Create a new skill config."""
    from backend.services.skill_config_service import create_skill as _create_skill
    skill_name = data.get("skill_name")
    if not skill_name:
        raise HTTPException(status_code=400, detail="skill_name is required")
    return _create_skill(
        skill_name=skill_name,
        secret_id=data.get("secret_id"),
        model_override=data.get("model_override"),
        prompt_template=data.get("prompt_template"),
    )


@router.patch("/skills/{skill_id}")
async def update_skill(skill_id: int, data: dict):
    """Update skill config (bind secret_id / model_override / etc.)."""
    from backend.services.skill_config_service import (
        get_skill as _get_skill,
        update_skill as _update_skill,
    )
    if _get_skill(skill_id) is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _update_skill(skill_id, **data)


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: int):
    """Delete a skill config."""
    from backend.services.skill_config_service import (
        get_skill as _get_skill,
        delete_skill as _delete_skill,
    )
    if _get_skill(skill_id) is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _delete_skill(skill_id)


@router.post("/skills/seed")
async def seed_skills():
    """Manually trigger preset skill seeding. Returns newly inserted count."""
    from backend.services.skill_config_service import seed_default_skills
    return {"seeded": seed_default_skills()}


# ── Obsidian ───────────────────────────────────────────────────

@router.post("/obsidian/open")
async def obsidian_open():
    """Return an obsidian://open URL for the knowledge vault."""
    from backend.services.obsidian_service import open_vault
    return open_vault()


@router.get("/obsidian/conflicts")
async def obsidian_conflicts():
    """List .md conflict snapshots recorded by the watchdog."""
    from backend.services.obsidian_service import get_conflicts
    return {"conflicts": get_conflicts()}


@router.post("/obsidian/watchdog/start")
async def obsidian_watchdog_start():
    """Start the knowledge watchdog."""
    from backend.services.knowledge_watcher import start_watcher, is_running
    start_watcher()
    return {"running": is_running()}


@router.post("/obsidian/watchdog/stop")
async def obsidian_watchdog_stop():
    """Stop the knowledge watchdog."""
    from backend.services.knowledge_watcher import stop_watcher, is_running
    stop_watcher()
    return {"running": is_running()}


@router.get("/obsidian/watchdog/status")
async def obsidian_watchdog_status():
    """Return the current watchdog running state."""
    from backend.services.knowledge_watcher import is_running
    return {"running": is_running()}


# ── Learning Plans ─────────────────────────────────────────────

@router.get("/plans")
async def list_plans(status: Optional[str] = Query(None)):
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
    """Trigger Agent to generate a learning plan via knowledge-master skill."""
    from backend.services.learning_service import generate_plan_task
    domains = data.get("domains")
    return generate_plan_task(domains=domains)


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
async def list_progress(domain: Optional[str] = Query(None)):
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

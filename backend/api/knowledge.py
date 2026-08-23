"""Knowledge API — CRUD for knowledge items, concepts, tasks, sync, health."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from backend.domain.knowledge_models import now_iso
from backend.exceptions import InvalidParamException
from backend.repository.knowledge_repo import knowledge_repo
from backend.services import ai_hub
from backend.version import APP_VERSION as API_VERSION

log = logging.getLogger("hotspot.api.knowledge")
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ── Items ───────────────────────────────────────────────────────

@router.get("/items")
async def list_items(
    domain: str | None = Query(None),
    source: str | None = Query(None),
    compiled: bool | None = Query(None),
    topic: str | None = Query(None),
    type: str | None = Query(None),
    difficulty: str | None = Query(None),
    since: str | None = Query(None),
    until: str | None = Query(None),
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
async def list_topics(domain: str | None = Query(None)):
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

    updatable = ["domain", "topic", "type", "difficulty", "tags", "concepts", "mastery"]
    for key in updatable:
        if key in data:
            setattr(item, key, data[key])

    item.updated_at = now_iso()
    knowledge_repo.upsert_item(item)
    ai_hub.write_item(item.to_dict(), agent="api:patch_item")
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
async def list_concepts(domain: str | None = Query(None)):
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
    domain: str | None = Query(None),
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


@router.get("/search")
async def search(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)):
    """Phase 1i Task 9.13: Federated search across hotspot + local wiki."""
    from backend.services.federation_service import search as do_search
    return do_search(query=q, limit=limit)


# ── Sync ────────────────────────────────────────────────────────

@router.post("/sync")
async def trigger_sync(source: str = Query("cubox")):
    """Trigger cubox sync as an async task. Returns task_id for polling."""

    import json as _json
    import threading

    from backend.repository.knowledge_repo import knowledge_repo
    from backend.services.cubox_sync import sync_cubox_with_progress

    if source not in ("cubox", "all"):
        raise InvalidParamException("only source=cubox or source=all is supported")

    # Create task record
    task = knowledge_repo.create_task(
        task_type="cubox_sync",
        params={"source": source, "limit": 100, "phase": "pending", "current": 0, "total": 0},
    )
    task_id = task.id

    def _run_sync():
        repo = knowledge_repo
        try:
            repo.update_task_status(task_id, "processing")
            repo.update_task_params(task_id, {"source": source, "phase": "connecting", "current": 0, "total": 0})

            def on_progress(phase: str, current: int, total: int):
                try:
                    repo.update_task_params(task_id, {
                        "source": source, "phase": phase, "current": current, "total": total,
                    })
                except Exception:
                    pass

            result = sync_cubox_with_progress(limit=100, on_progress=on_progress)
            repo.update_task_status(task_id, "done", result_path=_json.dumps(result))
            repo.update_task_params(task_id, {
                "source": source, "phase": "done",
                "current": result["total"], "total": result["total"],
                "result": result,
            })
        except Exception as e:
            repo.update_task_status(task_id, "failed", error_message=str(e))

    threading.Thread(target=_run_sync, daemon=True).start()

    return {"task_id": task_id, "status": "pending"}


# ── Tasks ───────────────────────────────────────────────────────

@router.post("/tasks")
async def create_task(data: dict):
    """Submit a task (e.g. generate_learning_plan)."""
    task_type = data.get("task_type", "unknown")
    params = data.get("params")
    task = knowledge_repo.create_task(task_type, params)
    return task.to_dict()


@router.get("/tasks")
async def list_tasks(status: str | None = Query(None)):
    """List knowledge tasks."""
    tasks = knowledge_repo.list_tasks(status=status)
    return {"tasks": [t.to_dict() for t in tasks]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: int):
    """Get a single knowledge task by id (for polling progress)."""
    import json
    task = knowledge_repo.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    # params is stored as JSON string in DB, parse it for frontend
    if isinstance(task.get("params"), str):
        try:
            task["params"] = json.loads(task["params"])
        except (json.JSONDecodeError, TypeError):
            pass
    return task


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
    """Import Chrome/Edge bookmarks into knowledge base.

    Supports two payload formats (Phase 1i Task 9.12):
    - JSON: ``{"bookmarks": <chrome roots dict>}`` → parse_chrome_bookmarks
    - HTML: ``{"html": "<Chrome export string>"}`` → parse_chrome_html
    """
    from backend.services.bookmark_sync import (
        import_bookmarks as do_import,
    )
    from backend.services.bookmark_sync import (
        parse_chrome_bookmarks,
        parse_chrome_html,
    )
    html = data.get("html")
    if isinstance(html, str) and html.strip():
        items = parse_chrome_html(html)
    else:
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


# ── Auto Classification (Phase 0) ─────────────────────────────

@router.post("/classify/batch")
async def classify_items_batch():
    """Run auto-classification on all items without domain assigned.

    Classifies domain/type/difficulty from tags, title, and source URL.
    Updates both .md files and SQLite.
    Returns count of items classified.
    """
    from backend.domain.knowledge_models import now_iso
    from backend.repository.knowledge_repo import knowledge_repo
    from backend.services.auto_classifier import batch_classify

    # Get all items without domain
    items = knowledge_repo.list_items(limit=10000)
    to_classify = [i.to_dict() for i in items if not i.domain]
    # write_item_to_md expects 'mastery' not 'mastered'
    for item_dict in to_classify:
        item_dict["mastery"] = item_dict.pop("mastered", 0)

    if not to_classify:
        return {"classified": 0, "message": "No items need classification"}

    classified = batch_classify(to_classify)
    count = 0
    for item_dict in classified:
        if item_dict.get("domain"):
            # Update SQLite
            item = knowledge_repo.get_item(item_dict["id"])
            if item:
                item.domain = item_dict["domain"]
                item.type = item_dict.get("type")
                item.difficulty = item_dict.get("difficulty")
                item.topic = item_dict.get("topic")
                item.updated_at = now_iso()
                knowledge_repo.upsert_item(item)
                # Update .md
                item_dict["mastery"] = item_dict.pop("mastery", 0)
                ai_hub.write_item(item_dict, agent="api:classify_batch")
                count += 1

    return {
        "classified": count,
        "total_unclassified": len(to_classify),
        "message": f"Classified {count} items",
    }


@router.get("/classify/stats")
async def classify_stats():
    """Show classification summary statistics."""
    from backend.repository.knowledge_repo import knowledge_repo
    items = knowledge_repo.list_items(limit=10000)
    domain_counts: dict[str, int] = {}
    compiled_count = 0
    for item in items:
        d = item.domain or "unclassified"
        domain_counts[d] = domain_counts.get(d, 0) + 1
        if item.compiled:
            compiled_count += 1
    return {
        "total": len(items),
        "classified": len(items) - domain_counts.get("unclassified", 0),
        "unclassified": domain_counts.get("unclassified", 0),
        "compiled": compiled_count,
        "by_domain": dict(sorted(domain_counts.items(), key=lambda x: -x[1])),
    }


# ── Concept Linking (Phase 0) ─────────────────────────────────

@router.post("/concepts/link/batch")
async def link_concepts_batch():
    """Auto-link tags to concepts for all items without concepts.

    Phase 1: Map existing tags to existing concept slugs.
    Phase 2: Auto-create new concept drafts for high-frequency tags.
    Updates both .md files and SQLite.
    Returns count of items linked and new concepts created.
    """
    from backend.domain.knowledge_models import now_iso
    from backend.repository.knowledge_repo import knowledge_repo
    from backend.services.concept_linker import batch_link_items
    from backend.services.knowledge_sync import sync_concept_to_db

    # Get all items that need linking
    items = knowledge_repo.list_items(limit=10000)
    to_link = [i.to_dict() for i in items if not i.concepts]
    # write_item_to_md expects 'mastery'
    for item_dict in to_link:
        item_dict["mastery"] = item_dict.pop("mastered", 0)

    if not to_link:
        return {"linked": 0, "new_concepts": 0, "message": "All items already have concepts"}

    # Count existing concepts before linking
    concepts_before = len(knowledge_repo.list_concepts())

    # Batch link
    linked = batch_link_items(to_link)
    count = 0
    for item_dict in linked:
        concepts = item_dict.get("concepts", [])
        if concepts:
            item = knowledge_repo.get_item(item_dict["id"])
            if item:
                item.concepts = concepts
                item.updated_at = now_iso()
                knowledge_repo.upsert_item(item)
                ai_hub.write_item(item_dict, agent="api:link_concepts_batch")
                count += 1

    # Sync newly created concept .md files to SQLite
    for f in Path(__file__).resolve().parent.parent.parent.glob("knowledge/concepts/*.md"):
        if f.stem == "graph":
            continue
        sync_concept_to_db(f)

    concepts_after = len(knowledge_repo.list_concepts())
    new_concepts = concepts_after - concepts_before

    return {
        "linked": count,
        "new_concepts": new_concepts,
        "total_linked": count,
        "message": f"Linked {count} items to concepts, created {new_concepts} new concepts",
    }


# ── Skills ──────────────────────────────────────────────────────
# Phase 7: skill_config_service 已删除 (Phase 5 内部 hotspot-agent 依赖)
# skills 端点降级为 deprecated, 永远返回 410 Gone

@router.get("/skills/{skill_name}/validate")
async def validate_skill(skill_name: str):
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回 410 Gone。"""
    raise HTTPException(
        status_code=410,
        detail={
            "message": "skill_config table dropped in v1.7.6 (Phase 7)",
            "migration": "migration 038",
        },
    )


@router.get("/skills")
async def list_skills(enabled: bool | None = Query(None)):
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回空列表。"""
    return {"version": API_VERSION, "deprecated": True, "skills": []}


@router.post("/skills")
async def create_skill(data: dict):
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回 410 Gone。"""
    raise HTTPException(
        status_code=410,
        detail={"message": "skill_config dropped in v1.7.6 (Phase 7)"},
    )


@router.patch("/skills/{skill_id}")
async def update_skill(skill_id: int, data: dict):
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回 410 Gone。"""
    raise HTTPException(
        status_code=410,
        detail={"message": "skill_config dropped in v1.7.6 (Phase 7)"},
    )


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: int):
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回 410 Gone。"""
    raise HTTPException(
        status_code=410,
        detail={"message": "skill_config dropped in v1.7.6 (Phase 7)"},
    )


@router.post("/skills/seed")
async def seed_skills():
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回 410 Gone。"""
    raise HTTPException(
        status_code=410,
        detail={"message": "skill_config dropped in v1.7.6 (Phase 7)"},
    )


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
    from backend.services.knowledge_watcher import is_running, start_watcher
    start_watcher()
    return {"running": is_running()}


@router.post("/obsidian/watchdog/stop")
async def obsidian_watchdog_stop():
    """Stop the knowledge watchdog."""
    from backend.services.knowledge_watcher import is_running, stop_watcher
    stop_watcher()
    return {"running": is_running()}


@router.get("/obsidian/watchdog/status")
async def obsidian_watchdog_status():
    """Return the current watchdog running state."""
    from backend.services.knowledge_watcher import is_running
    return {"running": is_running()}


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

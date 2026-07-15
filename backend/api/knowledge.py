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
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List knowledge items with optional filters."""
    items = knowledge_repo.list_items(domain=domain, source=source, compiled=compiled, limit=limit, offset=offset)
    total = knowledge_repo.count_items(domain=domain)
    return {"items": [i.to_dict() for i in items], "total": total}


@router.get("/items/{item_id}")
async def get_item(item_id: str):
    """Get a single knowledge item by ID."""
    item = knowledge_repo.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item.to_dict()


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

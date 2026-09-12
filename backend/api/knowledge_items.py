"""Knowledge API — items CRUD + topics + federated search.

拆自 ``backend/api/knowledge.py`` (Batch 2 任务 A): handler 逻辑原样搬移,
路径相对聚合层 (聚合层带 ``/api/knowledge`` prefix), URL 逐字不变。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.domain.knowledge_models import now_iso
from backend.repository.knowledge_repo import knowledge_repo
from backend.services import ai_hub
from backend.wiki_fs.paths import ITEMS_DIR

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


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
def get_item(item_id: str):
    """Get a single knowledge item by ID, with markdown content."""
    item = knowledge_repo.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    md_path = ITEMS_DIR / f"{item_id}.md"
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
    md_path = ITEMS_DIR / f"{item_id}.md"
    if md_path.exists():
        md_path.unlink()
    return {"deleted": item_id}


@router.get("/search")
async def search(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)):
    """Phase 1i Task 9.13: Federated search across hotspot + local wiki."""
    from backend.services.federation_service import search as do_search
    return do_search(query=q, limit=limit)

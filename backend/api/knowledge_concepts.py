"""Knowledge API — concepts + graph + federation + concept auto-linking.

拆自 ``backend/api/knowledge.py`` (Batch 2 任务 A): handler 逻辑原样搬移,
路径相对聚合层 (聚合层带 ``/api/knowledge`` prefix), URL 逐字不变。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.repository.knowledge_repo import knowledge_repo
from backend.services import ai_hub
from backend.wiki_fs.paths import CONCEPTS_DIR

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


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


@router.get("/federation")
async def get_federation():
    """Get local wiki federation status."""
    from backend.services.federation_service import get_federation_status
    return get_federation_status()


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
    for f in CONCEPTS_DIR.glob("*.md"):
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

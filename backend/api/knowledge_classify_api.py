"""knowledge_classify_api.py — /api/knowledge 自动分类查询面 (DEV-0287 D5 拆分)。

R3 行数守卫: knowledge_import.py 170>150 — 拆出 classify 两端点:
- ``POST /api/knowledge/classify/batch``  全量未分类条目批分类
- ``GET  /api/knowledge/classify/stats``  分类分布统计
URL/method 逐字不变 (同 prefix, 由 _registry 聚合挂载)。
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.services import ai_write_back

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


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
                ai_write_back.write_item(item_dict, agent="api:classify_batch")
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


__all__ = ["router"]

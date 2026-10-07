"""Knowledge API — imports + SOUL.md + compile + auto-classification.

拆自 ``backend/api/knowledge.py`` (Batch 2 任务 A): handler 逻辑原样搬移,
路径相对聚合层 (聚合层带 ``/api/knowledge`` prefix), URL 逐字不变。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


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


@router.post("/import-from-history")
async def import_from_history(data: dict):
    """Import archived hotspot items into knowledge base.

    item_ids 是 hotspots 表的 TEXT 主键 (如 "ai_量子位_0").
    """
    from backend.services.history_import import import_from_history as do_import
    item_ids = data.get("item_ids", [])
    return do_import(item_ids)


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


@router.post("/projection/rebuild")
async def rebuild_projection():
    """手动触发 md→SQLite 投影全量重建 (wiki-first 契约, DEV-0241)。

    与每日 04:10 ``wiki_projection_rebuild`` job 同一实现: items/concepts
    全量 upsert + 孤儿行清理, 幂等。用于 warm 库丢失/断层后的手动恢复。
    """
    import time as _time

    from backend.services.knowledge_sync import (
        full_sync_concepts_to_db,
        full_sync_items_to_db,
    )

    t0 = _time.time()
    items = full_sync_items_to_db()
    concepts = full_sync_concepts_to_db()
    return {
        "items": items,
        "concepts": concepts,
        "elapsed_ms": int((_time.time() - t0) * 1000),
    }


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


# ---------------------------------------------------------------------------
# classify/batch + classify/stats
# DEV-0287 (D5): 170>150 拆出 → knowledge_classify_api.py (同 prefix 聚合挂载, URL 零变更)

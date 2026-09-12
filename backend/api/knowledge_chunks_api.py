"""Knowledge chunks API — chunk CRUD, FTS5 search, and chunk generation.

Endpoints
---------
- GET  /api/knowledge/chunks/{item_id}     — list chunks for an item
- GET  /api/knowledge/chunks/search?q=...  — FTS5 full-text search
- POST /api/knowledge/chunks/generate/{item_id} — generate chunks from .md
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

log = logging.getLogger("hotspot.api.knowledge_chunks")
router = APIRouter(prefix="/api/knowledge/chunks", tags=["knowledge-chunks"])


# ── List chunks ─────────────────────────────────────────────────


@router.get("/{item_id}")
def get_chunks(item_id: str):
    """Return all chunks for a knowledge item, ordered by chunk_index."""
    from backend.services.chunk_service import list_chunks

    return {"chunks": list_chunks(item_id)}


# ── FTS5 search ─────────────────────────────────────────────────


@router.get("/search")
def search_chunks(q: str = Query(..., min_length=1)):
    """FTS5 full-text search across knowledge chunks (v0.4.0: 中文路由).

    - 含中文且长度 ≥3 → trigram 表 (knowledge_chunks_fts_cjk), 支持 CJK 子串
    - 纯 ASCII → unicode61 表 (knowledge_chunks_fts)
    - FTS 无命中或 2 字短查询 → LIKE 回退 (chunks 规模小, LIKE 足够)
    """
    from backend.services.chunk_service import search_chunks as _search

    return _search(q)


# ── Generate chunks ─────────────────────────────────────────────


@router.post("/generate/{item_id}")
async def generate_chunks(item_id: str):
    """Split a knowledge item's .md content into chunks (v0.4.0: 委托 chunk_service).

    Reads the markdown file from ``knowledge/items/{item_id}.md``,
    strips YAML frontmatter, splits by paragraphs, and writes each
    paragraph as a row in ``knowledge_chunks`` (FTS5 由触发器同步).

    Returns **409 Conflict** if chunks already exist for this item.
    """
    from backend.services.chunk_service import generate_chunks_for_item, list_chunks

    result = await asyncio.to_thread(generate_chunks_for_item, item_id)
    if result.get("skipped") and result.get("reason") == "already_exists":
        raise HTTPException(status_code=409, detail="Chunks already exist for this item")
    if result.get("skipped") and result.get("reason") == "item_not_found":
        raise HTTPException(status_code=404, detail="Item not found")
    if result.get("skipped") and result.get("reason") == "no_md_file":
        raise HTTPException(status_code=404, detail="Item markdown file not found")
    if result.get("skipped") and result.get("reason") == "too_short":
        raise HTTPException(status_code=400, detail="Item has no content to chunk")
    # 返回兼容结构
    return {
        "chunks": list_chunks(item_id, include_created_at=False),
        "created": result.get("created", 0),
    }

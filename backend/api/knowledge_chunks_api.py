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
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from backend.repository.db import get_connection
from backend.repository.knowledge_repo import knowledge_repo

log = logging.getLogger("hotspot.api.knowledge_chunks")
router = APIRouter(prefix="/api/knowledge/chunks", tags=["knowledge-chunks"])


# ── List chunks ─────────────────────────────────────────────────


@router.get("/{item_id}")
async def get_chunks(item_id: str):
    """Return all chunks for a knowledge item, ordered by chunk_index."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, item_id, chunk_index, content, char_start, char_end, summary, created_at "
        "FROM knowledge_chunks WHERE item_id = ? ORDER BY chunk_index",
        (item_id,),
    ).fetchall()
    return {"chunks": [dict(r) for r in rows]}


# ── FTS5 search ─────────────────────────────────────────────────


@router.get("/search")
async def search_chunks(q: str = Query(..., min_length=1)):
    """FTS5 full-text search across knowledge chunks (v0.4.0: 中文路由).

    - 含中文且长度 ≥3 → trigram 表 (knowledge_chunks_fts_cjk), 支持 CJK 子串
    - 纯 ASCII → unicode61 表 (knowledge_chunks_fts)
    - FTS 无命中或 2 字短查询 → LIKE 回退 (chunks 规模小, LIKE 足够)
    """
    import re as _re

    conn = get_connection()
    sanitized = q.replace('"', '""')
    has_cjk = bool(_re.search(r"[\u4e00-\u9fff]", q))

    def _search_fts() -> list:
        if has_cjk and len(q) >= 3:
            # trigram 表 (FTS5 trigram 要求查询 ≥3 字符)
            try:
                return conn.execute(
                    """
                    SELECT c.item_id, c.chunk_index,
                           substr(c.content, 1, 120) AS content_snippet,
                           c.summary
                    FROM knowledge_chunks_fts_cjk
                    JOIN knowledge_chunks c ON knowledge_chunks_fts_cjk.rowid = c.id
                    WHERE knowledge_chunks_fts_cjk MATCH ?
                    ORDER BY rank
                    LIMIT 50
                    """,
                    (sanitized,),
                ).fetchall()
            except Exception as exc:
                log.warning("CJK FTS5 query failed: %s — %r", exc, q)
                return []
        # unicode61 (ASCII)
        try:
            return conn.execute(
                """
                SELECT c.item_id, c.chunk_index,
                       snippet(knowledge_chunks_fts, 0, '<b>', '</b>', '...', 64) AS content_snippet,
                       c.summary
                FROM knowledge_chunks_fts
                JOIN knowledge_chunks c ON knowledge_chunks_fts.rowid = c.id
                WHERE knowledge_chunks_fts MATCH ?
                ORDER BY rank
                LIMIT 50
                """,
                (sanitized,),
            ).fetchall()
        except Exception as exc:
            log.warning("FTS5 query failed: %s — query=%r", exc, q)
            return []

    rows = _search_fts()
    # 回退: FTS 无命中 (或 2 字短查询) → LIKE 全文模糊匹配
    if not rows:
        like = f"%{q}%"
        try:
            rows = conn.execute(
                "SELECT id AS item_id, chunk_index, "
                "substr(content, 1, 120) AS content_snippet, summary "
                "FROM knowledge_chunks "
                "WHERE content LIKE ? OR summary LIKE ? LIMIT 50",
                (like, like),
            ).fetchall()
        except Exception:
            rows = []

    results = [dict(r) for r in rows]
    return {"results": results, "total": len(results)}


# ── Generate chunks ─────────────────────────────────────────────


@router.post("/generate/{item_id}")
async def generate_chunks(item_id: str):
    """Split a knowledge item's .md content into chunks (v0.4.0: 委托 chunk_service).

    Reads the markdown file from ``knowledge/items/{item_id}.md``,
    strips YAML frontmatter, splits by paragraphs, and writes each
    paragraph as a row in ``knowledge_chunks`` (FTS5 由触发器同步).

    Returns **409 Conflict** if chunks already exist for this item.
    """
    from backend.services.chunk_service import generate_chunks_for_item

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
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, item_id, chunk_index, content, char_start, char_end, summary "
        "FROM knowledge_chunks WHERE item_id = ? ORDER BY chunk_index",
        (item_id,),
    ).fetchall()
    return {"chunks": [dict(r) for r in rows], "created": result.get("created", 0)}

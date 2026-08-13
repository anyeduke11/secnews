"""Knowledge chunks API — chunk CRUD, FTS5 search, and chunk generation.

Endpoints
---------
- GET  /api/knowledge/chunks/{item_id}     — list chunks for an item
- GET  /api/knowledge/chunks/search?q=...  — FTS5 full-text search
- POST /api/knowledge/chunks/generate/{item_id} — generate chunks from .md
"""

from __future__ import annotations

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
    """FTS5 full-text search across knowledge_chunks_fts.

    Returns matching chunks with a content snippet via FTS5's built-in
    ``snippet()`` function.  The query is plain FTS5 syntax — special
    characters (``*``, ``"``, ``AND`` / ``OR`` / ``NOT``) are passed
    through as-is so the user can write advanced queries.
    """
    conn = get_connection()
    # Escape embedded double quotes to avoid FTS5 syntax errors while
    # preserving the rest of the FTS5 query syntax.
    sanitized = q.replace('"', '""')
    try:
        rows = conn.execute(
            """
            SELECT c.item_id, c.chunk_index,
                   snippet(knowledge_chunks_fts, 0, '<b>', '</b>', '...', 64) AS content_snippet,
                   c.summary
            FROM knowledge_chunks_fts
            JOIN knowledge_chunks c ON knowledge_chunks_fts.rowid = c.id
            WHERE knowledge_chunks_fts MATCH ?
            ORDER BY rank
            """,
            (sanitized,),
        ).fetchall()
    except Exception as exc:
        log.warning("FTS5 query failed: %s — query=%r", exc, q)
        raise HTTPException(status_code=400, detail=f"Invalid search query: {exc}") from exc

    results = [dict(r) for r in rows]
    return {"results": results, "total": len(results)}


# ── Generate chunks ─────────────────────────────────────────────


@router.post("/generate/{item_id}")
async def generate_chunks(item_id: str):
    """Split a knowledge item's .md content into chunks.

    Reads the markdown file from ``knowledge/items/{item_id}.md``,
    strips YAML frontmatter, splits by double-newline paragraphs, and
    writes each paragraph as a row in ``knowledge_chunks``.

    Returns **409 Conflict** if chunks already exist for this item.
    """
    # 1. Verify item exists in DB.
    item = knowledge_repo.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    # 2. Check for existing chunks.
    conn = get_connection()
    existing = conn.execute(
        "SELECT COUNT(*) FROM knowledge_chunks WHERE item_id = ?", (item_id,)
    ).fetchone()[0]
    if existing > 0:
        raise HTTPException(
            status_code=409,
            detail="Chunks already exist for this item",
        )

    # 3. Read .md file and strip frontmatter.
    md_path = (
        Path(__file__).resolve().parent.parent.parent
        / "knowledge"
        / "items"
        / f"{item_id}.md"
    )
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Item markdown file not found")

    raw = md_path.read_text(encoding="utf-8")
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        content = parts[2].strip() if len(parts) >= 3 else ""
    else:
        content = raw.strip()

    if not content:
        raise HTTPException(status_code=400, detail="Item has no content to chunk")

    # 4. Split by double newline into paragraphs.
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    chunks = []
    char_pos = 0
    for idx, para in enumerate(paragraphs):
        # Locate the paragraph within the original content string.
        cs = content.find(para, char_pos)
        ce = cs + len(para)
        char_pos = ce

        # First ~100 chars as a simple summary.
        summary = (para[:100] + "...") if len(para) > 100 else para

        conn.execute(
            "INSERT INTO knowledge_chunks "
            "(item_id, chunk_index, content, char_start, char_end, summary) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (item_id, idx, para, cs, ce, summary),
        )
        chunks.append(
            {
                "item_id": item_id,
                "chunk_index": idx,
                "content": para,
                "char_start": cs,
                "char_end": ce,
                "summary": summary,
            }
        )

    return {"chunks": chunks, "created": len(chunks)}
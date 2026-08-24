"""KL Pipeline REST API — wiki items, pipeline control, concepts, graph.

Routes for the KL knowledge pipeline: import, inbox scan, pipeline
control (drain/advance/retry), item CRUD, concept listing, and graph.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.kl_pipeline import KLPipeline, KLQueue
from backend.kl_pipeline.obs.funnel import funnel_stats
from backend.kl_pipeline.obs.ledger import TokenLedger
from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.wiki_fs import WikiFs

router = APIRouter(prefix="/api/kl", tags=["kl-pipeline"])

# Lazy-initialized singletons.
_wiki_fs: WikiFs | None = None
_pipeline: KLPipeline | None = None


def _get_wiki_fs() -> WikiFs:
    global _wiki_fs
    if _wiki_fs is None:
        from backend.config import config
        import os
        root = os.path.join(os.path.dirname(config.db_path), "..", "knowledge")
        _wiki_fs = WikiFs(root)
    return _wiki_fs


def _get_pipeline() -> KLPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = KLPipeline(wiki_fs=_get_wiki_fs())
    return _pipeline


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class ImportUrlRequest(BaseModel):
    url: str


class ImportBookmarksRequest(BaseModel):
    html: str


class AdvanceRequest(BaseModel):
    item_id: str


class RetryRequest(BaseModel):
    wiki_id: str | None = None


class UpdateItemRequest(BaseModel):
    fm: dict | None = None
    body: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/import/url")
async def import_url(req: ImportUrlRequest) -> dict:
    """Import a URL as a new wiki item (fetch → kl:raw)."""
    wiki_fs = _get_wiki_fs()
    # For Phase 0, we create a stub item. Full fetch is in Phase 1.
    result = wiki_fs.ingest_url(req.url, title=req.url, text="")
    pipeline = _get_pipeline()
    pipeline.kickoff(result["id"])
    return result


@router.post("/import/bookmarks")
async def import_bookmarks(req: ImportBookmarksRequest) -> dict:
    """Import Netscape bookmark HTML."""
    wiki_fs = _get_wiki_fs()
    return wiki_fs.import_bookmarks(req.html)


@router.post("/inbox/scan")
async def scan_inbox() -> dict:
    """Scan inbox/ and move items to items/ or quarantine/."""
    wiki_fs = _get_wiki_fs()
    return wiki_fs.scan_inbox()


@router.get("/pipeline/stats")
async def pipeline_stats() -> dict:
    """Funnel + queue + dead-letter + token ledger stats."""
    pipeline = _get_pipeline()
    wiki_fs = _get_wiki_fs()
    funnel = funnel_stats(wiki_fs)
    queue_stats = pipeline.queue.stats()
    errors = pipeline.queue.errors(limit=10)
    ledger = TokenLedger(get_connection()).summary()
    return {"funnel": funnel, "queue": queue_stats, "errors": errors, "ledger": ledger}


@router.post("/pipeline/drain")
async def drain_pipeline() -> dict:
    """Manually consume due pipeline tasks."""
    pipeline = _get_pipeline()
    return pipeline.drain_due()


@router.post("/pipeline/advance")
async def advance_item(req: AdvanceRequest) -> dict:
    """Advance a single item to its next stage."""
    pipeline = _get_pipeline()
    try:
        new_stage = pipeline.advance(req.item_id)
        return {"item_id": req.item_id, "new_stage": new_stage}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)})


@router.post("/pipeline/retry")
async def retry_errors(req: RetryRequest) -> dict:
    """Retry error tasks (optionally filtered by wiki_id)."""
    pipeline = _get_pipeline()
    count = pipeline.retry_errors(req.wiki_id)
    return {"retried": count}


@router.get("/items/{item_id}")
async def get_item(item_id: str) -> dict:
    """Get a wiki item's frontmatter + body."""
    wiki_fs = _get_wiki_fs()
    doc = wiki_fs.read_item(item_id)
    if doc is None:
        raise HTTPException(status_code=404, detail={"message": "item not found", "missing": item_id})
    return doc


@router.put("/items/{item_id}")
async def update_item(item_id: str, req: UpdateItemRequest) -> dict:
    """Update a wiki item's frontmatter (one-way projection)."""
    wiki_fs = _get_wiki_fs()
    doc = wiki_fs.read_item(item_id)
    if doc is None:
        raise HTTPException(status_code=404, detail={"message": "item not found", "missing": item_id})
    if req.fm is not None:
        doc["fm"].update(req.fm)
    if req.body is not None:
        doc["body"] = req.body
    wiki_fs.write_item(item_id, doc)
    return {"status": "ok"}


@router.get("/concepts")
async def list_concepts() -> dict:
    """List all concept cards."""
    wiki_fs = _get_wiki_fs()
    concepts = wiki_fs.list_concepts()
    return {"concepts": concepts, "total": len(concepts)}


@router.get("/graph")
async def get_graph() -> dict:
    """Return knowledge graph edges."""
    import json
    from pathlib import Path
    wiki_fs = _get_wiki_fs()
    graph_path = Path(wiki_fs.root) / "graph.json"
    if graph_path.exists():
        try:
            return json.loads(graph_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"nodes": {}, "edges": {}}

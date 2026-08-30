"""KL Pipeline REST API — wiki items, pipeline control, concepts, graph.

Routes for the KL knowledge pipeline: import, inbox scan, pipeline
control (drain/advance/retry), item CRUD, concept listing, and graph.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.kl_pipeline import KLPipeline
from backend.kl_pipeline.obs.ledger import TokenLedger
from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.wiki_fs import WikiFs

router = APIRouter(prefix="/api/kl", tags=["kl-pipeline"])


def _get_wiki_fs() -> WikiFs:
    from backend.kl_pipeline.runtime import get_production_wiki_fs
    return get_production_wiki_fs()


def _log_ingest_event(kind: str, item_id: str, payload: dict) -> None:
    """导入留痕 wiki_events (DB=事件管理层)。失败不阻塞导入本身。"""
    try:
        from backend.repository.wiki_event_repo import wiki_event_repo
        wiki_event_repo.log(
            kind=kind,
            wiki_path=f"items/{item_id}.md",
            agent="api:kl_import",
            payload=payload,
        )
    except Exception as exc:
        logger.warning(f"kl import wiki_events log failed: {exc}")


def _get_pipeline() -> KLPipeline:
    from backend.kl_pipeline.runtime import get_production_pipeline
    return get_production_pipeline()


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
    _log_ingest_event("ingest_url", result["id"], {"url": req.url})
    pipeline = _get_pipeline()
    pipeline.kickoff(result["id"])
    return result


@router.post("/import/bookmarks")
async def import_bookmarks(req: ImportBookmarksRequest) -> dict:
    """Import Netscape bookmark HTML."""
    wiki_fs = _get_wiki_fs()
    result = wiki_fs.import_bookmarks(req.html)
    if result.get("added"):
        _log_ingest_event("ingest_bookmarks", "batch", {
            "added": result.get("added"), "dup": result.get("dup"),
        })
    return result


@router.post("/inbox/scan")
async def scan_inbox() -> dict:
    """Scan inbox/ and move items to items/ or quarantine/."""
    wiki_fs = _get_wiki_fs()
    result = wiki_fs.scan_inbox()
    # S1-5: 扫描后附带 quarantine 清单，前端一次性拿到处置结果
    result["quarantine_files"] = wiki_fs.list_quarantine()
    return result


@router.get("/inbox/list")
async def list_inbox() -> dict:
    """S1-5: 列出 inbox/ 待处理文件。"""
    return {"files": _get_wiki_fs().list_inbox()}


@router.get("/quarantine/list")
async def list_quarantine() -> dict:
    """S1-5: 列出 quarantine/ 隔离区文件。"""
    return {"files": _get_wiki_fs().list_quarantine()}


@router.get("/pipeline/stats")
async def pipeline_stats() -> dict:
    """Funnel + queue + dead-letter + alive + token ledger stats.

    口径 (v0.6.3 P0-1 卡顿根治): ``funnel`` 改读 **DB 投影**
    ``warm.knowledge_items.lifecycle`` —— T1–T5 触发器读写的就是这张表,
    这才是管线真实口径 (历史 md 口径 kl:raw=48 vs DB=2, 见 git blame)。
    liveness (书签存活) 仍按 md frontmatter 统计 (``alive`` 字段尚无 DB
    投影), 30s TTL 缓存 + to_thread, 不再阻塞事件循环。
    """
    import asyncio

    from backend.services.wiki_stats_service import (
        funnel_from_db,
        liveness_from_md_cached,
    )

    pipeline = _get_pipeline()
    wiki_fs = _get_wiki_fs()
    funnel = await asyncio.to_thread(funnel_from_db)
    queue_stats = pipeline.queue.stats()
    errors = pipeline.queue.errors(limit=10)
    ledger = TokenLedger(get_connection()).summary()
    alive = await asyncio.to_thread(liveness_from_md_cached, wiki_fs)
    return {
        "funnel": funnel,
        "funnel_source": "db_knowledge_items_lifecycle",
        "funnel_counts_items": sum(int(f.get("count") or 0) for f in funnel),
        "funnel_note": "按 DB warm.knowledge_items.lifecycle 统计 (T1-T5 管线真实口径, 与 md 归档数字不同)",
        "queue": queue_stats,
        "queue_source": "kl_queue_table",
        "queue_note": "待处理任务队列, 非全量条目数",
        "errors": errors,
        "alive": alive,
        "ledger": ledger,
    }


@router.get("/liveness")
async def liveness_stats() -> dict:
    """书签存活三态分布 (md frontmatter 口径, 30s TTL 缓存 + to_thread)。"""
    import asyncio

    from backend.services.wiki_stats_service import liveness_from_md_cached

    return await asyncio.to_thread(liveness_from_md_cached, _get_wiki_fs())


@router.post("/liveness/sweep")
async def liveness_sweep() -> dict:
    """手动触发一次书签存活批扫 (HEAD+GET 兜底, 三态写回 frontmatter)。

    网络密集操作 → asyncio.to_thread, 不阻塞事件循环。
    """
    import asyncio

    from backend.wiki_fs.liveness import sweep_liveness

    wiki_fs = _get_wiki_fs()
    stats = await asyncio.to_thread(sweep_liveness, wiki_fs)
    _log_ingest_event("liveness_sweep", "batch", dict(stats))
    return stats


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
def get_graph() -> dict:
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

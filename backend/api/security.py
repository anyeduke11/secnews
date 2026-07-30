"""Phase 4 Security Graph API — /api/security/*

Endpoints
---------
- GET /api/security/entities               — list/search security entities
- GET /api/security/entities/{id}         — get single entity
- GET /api/security/entities/{id}/related — get related entities
- GET /api/security/graph                 — build security knowledge graph
- POST /api/security/enrich               — enrich a hotspot item
- POST /api/security/mitre/sync           — trigger MITRE ATT&CK sync
- POST /api/security/terminology/normalize — normalize a term
- GET  /api/security/terminology/search    — search terms
- GET  /api/security/terminology/taxonomy  — get term taxonomy
- GET  /api/security/terminology/suggest   — suggest tags from text
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from backend.repository.security_repo import SecurityRepository
from backend.services.security_graph_service import SecurityGraphService
from backend.services.terminology_service import TerminologyService

router = APIRouter(prefix="/api/security", tags=["security"])
_repo = SecurityRepository()
_svc = SecurityGraphService()


class MitreSyncResponse(BaseModel):
    ok: bool
    count: int
    message: str


@router.get("/entities")
async def list_entities(
    request: Request,
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    q: Optional[str] = Query(None, description="Search by name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List security entities, optionally filtered by type or name search."""
    try:
        if q:
            items = _repo.search_entities(q, entity_types=[entity_type] if entity_type else None)
            total = len(items)
            return {"ok": True, "items": items[:limit], "total": total}
        items, total = _repo.list_entities(
            entity_type=entity_type,
            limit=limit,
            offset=offset,
        )
        return {"ok": True, "items": items, "total": total}
    except Exception as e:
        from backend.exceptions import InternalException
        raise InternalException(f"list entities failed: {e}")


@router.get("/entities/{entity_id}")
async def get_entity(request: Request, entity_id: str):
    """Get a single security entity by ID."""
    try:
        row = _repo.get_entity(entity_id)
        if not row:
            from backend.exceptions import NotFoundException
            raise NotFoundException(f"entity {entity_id} not found")
        return {"ok": True, "item": row}
    except Exception as e:
        from backend.exceptions import InternalException
        raise InternalException(f"get entity failed: {e}")


@router.get("/entities/{entity_id}/related")
async def get_related(request: Request, entity_id: str, depth: int = Query(1, ge=1, le=3)):
    """Get related entities (default depth=1)."""
    try:
        result = _repo.get_related(entity_id, depth=depth)
        return {"ok": True, **result}
    except Exception as e:
        from backend.exceptions import InternalException
        raise InternalException(f"get related failed: {e}")


@router.get("/graph")
async def get_security_graph(
    request: Request,
    view: str = Query("full", description="Graph view: full, attack, cve, compliance"),
):
    """Build security knowledge graph.

    Args:
        view: 'full' - all entities, 'attack' - ATT&CK only,
              'cve' - CVEs only, 'compliance' - compliance only
    """
    try:
        result = await asyncio.to_thread(_svc.get_graph, view=view)
        return {"ok": True, **result}
    except Exception as e:
        from backend.exceptions import InternalException
        raise InternalException(f"build security graph failed: {e}")


@router.post("/enrich")
async def enrich_item(request: Request, item: dict):
    """Enrich a single hotspot/knowledge item with security entity IDs."""
    try:
        result = await asyncio.to_thread(_svc.enrich_hotspot_item, item)
        return {"ok": True, "enriched": result}
    except Exception as e:
        from backend.exceptions import InternalException
        raise InternalException(f"enrich item failed: {e}")


@router.post("/mitre/sync", response_model=MitreSyncResponse)
async def trigger_mitre_sync(request: Request, clear: bool = Query(False)):
    """Manually trigger MITRE ATT&CK sync.

    Args:
        clear: if True, delete all existing ATT&CK rows before syncing.
    """
    try:
        from backend.security.mitre_attack import MitreAttackClient
        client = MitreAttackClient()
        count = await asyncio.to_thread(client.sync_to_db, clear=clear)
        return MitreSyncResponse(ok=True, count=count, message=f"synced {count} entities")
    except Exception as e:
        from backend.exceptions import InternalException
        raise InternalException(f"mitre sync failed: {e}")


# ---------------------------------------------------------------------------
# Terminology API
# ---------------------------------------------------------------------------
_term_svc = TerminologyService()


@router.post("/terminology/normalize")
async def normalize_term(request: Request, text: str = Query(..., description="Term to normalize")):
    """Normalize a free-text term to canonical form."""
    try:
        result = await asyncio.to_thread(_term_svc.normalize, text)
        return {"ok": True, **result}
    except Exception as e:
        from backend.exceptions import InternalException
        raise InternalException(f"normalize term failed: {e}")


@router.get("/terminology/search")
async def search_terms(
    request: Request,
    q: str = Query(..., description="Search query"),
    term_type: Optional[str] = Query(None, description="Filter by term type"),
    limit: int = Query(20, ge=1, le=100),
):
    """Search canonical terms."""
    try:
        results = await asyncio.to_thread(_term_svc.search, q, term_type=term_type, limit=limit)
        return {"ok": True, "items": results}
    except Exception as e:
        from backend.exceptions import InternalException
        raise InternalException(f"search terms failed: {e}")


@router.get("/terminology/taxonomy")
async def get_taxonomy(
    request: Request,
    term_type: Optional[str] = Query(None, description="Filter by term type"),
):
    """Get term taxonomy hierarchy."""
    try:
        results = await asyncio.to_thread(_repo.get_taxonomy, term_type=term_type)
        return {"ok": True, "items": results}
    except Exception as e:
        from backend.exceptions import InternalException
        raise InternalException(f"get taxonomy failed: {e}")


@router.get("/terminology/suggest")
async def suggest_tags(
    request: Request,
    title: str = Query(..., description="Article title"),
    content: str = Query("", description="Article content (optional)"),
):
    """Suggest security terms from title and content."""
    try:
        results = await asyncio.to_thread(_term_svc.suggest_tags, title, content)
        return {"ok": True, "suggestions": results}
    except Exception as e:
        from backend.exceptions import InternalException
        raise InternalException(f"suggest tags failed: {e}")


__all__ = ["router"]

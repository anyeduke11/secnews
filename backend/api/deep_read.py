"""DeepRead 深度分析面板 API (Phase 4 S4-2)。

- ``POST /api/deep-read/{entity_type}/{entity_id}?force=true|false``: 触发/复用 4 节 LLM 分析
- ``GET  /api/deep-read/{entity_type}/{entity_id}``: 读 (无则 404)
- ``GET  /api/deep-read/recent?limit=N``: 最近深读列表

支持的 entity_type: hotspot / cve / wiki。
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.exceptions import HotspotException
from backend.logging_config import logger
from backend.services.deep_read_service import DeepReadError, DeepReadService

router = APIRouter(prefix="/api/deep-read", tags=["deep-read"])


# ── Response Models ──────────────────────────────────────────


class DeepReadSectionResponse(BaseModel):
    summary: str = ""
    impact: str = ""
    relations: str = ""
    risks: str = ""


class DeepReadResponse(BaseModel):
    entity_type: str
    entity_id: str
    content_md: str
    sections: DeepReadSectionResponse
    sections_json: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    created_at: str
    updated_at: str


def _to_response(item_dict: dict[str, Any]) -> DeepReadResponse:
    sections_raw = item_dict.get("sections") or {}
    if not isinstance(sections_raw, dict):
        sections_raw = {}
    return DeepReadResponse(
        entity_type=item_dict.get("entity_type", ""),
        entity_id=item_dict.get("entity_id", ""),
        content_md=item_dict.get("content_md", ""),
        sections=DeepReadSectionResponse(
            summary=str(sections_raw.get("summary", "")),
            impact=str(sections_raw.get("impact", "")),
            relations=str(sections_raw.get("relations", "")),
            risks=str(sections_raw.get("risks", "")),
        ),
        sections_json=item_dict.get("sections_json", "{}"),
        provider=str(item_dict.get("provider", "")),
        model=str(item_dict.get("model", "")),
        tokens_in=int(item_dict.get("tokens_in", 0)),
        tokens_out=int(item_dict.get("tokens_out", 0)),
        cost_usd=float(item_dict.get("cost_usd", 0.0)),
        latency_ms=int(item_dict.get("latency_ms", 0)),
        created_at=str(item_dict.get("created_at", "")),
        updated_at=str(item_dict.get("updated_at", "")),
    )


def _err_to_http(e: Exception) -> HTTPException:
    if isinstance(e, DeepReadError):
        return HTTPException(status_code=502, detail={"message": str(e)})
    if isinstance(e, HotspotException):
        return HTTPException(status_code=e.http_status, detail={"message": e.message})
    return HTTPException(status_code=500, detail={"message": f"deep read failed: {e}"})


# ── Endpoints ────────────────────────────────────────────────


@router.get("/recent", response_model=list[DeepReadResponse])
async def list_recent(
    limit: int = Query(20, ge=1, le=200, description="返回条目上限"),
) -> list[DeepReadResponse]:
    """最近深读列表 (按 updated_at 倒序)。"""
    svc = DeepReadService()
    try:
        items = await asyncio.to_thread(svc.list_recent, limit)
    except Exception as e:
        raise _err_to_http(e)
    return [_to_response(it) for it in items]


@router.get("/{entity_type}/{entity_id}", response_model=DeepReadResponse)
async def fetch(entity_type: str, entity_id: str) -> DeepReadResponse:
    """读 deep_reads 表 (无 → 404, 不触发 LLM)。"""
    svc = DeepReadService()
    try:
        item = await asyncio.to_thread(svc.fetch, entity_type, entity_id)
    except Exception as e:
        raise _err_to_http(e)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"deep_read not found: {entity_type}/{entity_id}"},
        )
    return _to_response(item.to_dict())


@router.post("/{entity_type}/{entity_id}", response_model=DeepReadResponse)
async def run(
    entity_type: str,
    entity_id: str,
    force: bool = Query(False, description="force=true 时覆盖已有分析"),
) -> DeepReadResponse:
    """触发或复用 4 节 LLM 分析。

    - 表里有且 force=false → 直接返回 (cache 命中, 不调 LLM)
    - 否则 → 拉原文 → LLM → 4 节 JSON → UPSERT
    - LLM 失败 → 502, 表不污染
    """
    svc = DeepReadService()
    try:
        item = await svc.run(entity_type, entity_id, force=force)
    except DeepReadError as e:
        logger.warning("DeepRead failed: %s/%s — %s", entity_type, entity_id, e)
        raise _err_to_http(e)
    except Exception as e:
        logger.exception("DeepRead unexpected error: %s/%s", entity_type, entity_id)
        raise _err_to_http(e)
    return _to_response(item.to_dict())


__all__ = ["router"]
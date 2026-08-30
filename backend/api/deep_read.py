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


class DeepReadSectionItem(BaseModel):
    """一节解读。``tone`` ∈ {mint, amber, red} (哨兵终端语义三色锁)。"""

    key: str
    title: str
    tone: str = "mint"
    body: str = ""


# 旧行 (v1 envelope 之前的扁平 4 键) 的标题兜底, 保证历史缓存仍渲染出小标题
_LEGACY_SECTION_TITLES: dict[str, str] = {
    "summary": "摘要",
    "impact": "影响",
    "relations": "关联",
    "risks": "风险",
}


class DeepReadResponse(BaseModel):
    entity_type: str
    entity_id: str
    content_md: str
    category: str = ""
    sections: list[DeepReadSectionItem]
    sections_json: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    created_at: str
    updated_at: str


def _build_sections(item_dict: dict[str, Any]) -> list[DeepReadSectionItem]:
    """分节渲染源: 优先 v1 有序定义, 旧行回落扁平键 + 中文标题表。"""
    defs = item_dict.get("section_defs") or []
    if isinstance(defs, list) and defs:
        out = []
        for d in defs:
            if not isinstance(d, dict) or not d.get("key"):
                continue
            out.append(
                DeepReadSectionItem(
                    key=str(d["key"]),
                    title=str(d.get("title") or d["key"]),
                    tone=str(d.get("tone") or "mint"),
                    body=str(d.get("body") or ""),
                )
            )
        if out:
            return out

    sections_raw = item_dict.get("sections") or {}
    if not isinstance(sections_raw, dict):
        return []
    return [
        DeepReadSectionItem(
            key=str(k),
            title=_LEGACY_SECTION_TITLES.get(str(k), str(k)),
            body=str(v or ""),
        )
        for k, v in sections_raw.items()
    ]


def _to_response(item_dict: dict[str, Any]) -> DeepReadResponse:
    return DeepReadResponse(
        entity_type=item_dict.get("entity_type", ""),
        entity_id=item_dict.get("entity_id", ""),
        content_md=item_dict.get("content_md", ""),
        category=str(item_dict.get("category") or ""),
        sections=_build_sections(item_dict),
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
        # svc.fetch 是 async 方法: 直接 await。
        # 此前用 asyncio.to_thread 包它, 拿到的是**从未被 await 的协程对象**,
        # 下一行 item.to_dict() 直接 AttributeError → 本端点恒定 500,
        # 存好的解读永远读不回来 (只有 POST 重新生成那条路能出数据)。
        item = await svc.fetch(entity_type, entity_id)
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
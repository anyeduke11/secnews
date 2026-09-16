"""v1.7 Phase 2 — Annotations API (笔记空间)。

路由清单
--------
- ``GET    /api/annotations``                   列出某对象的笔记 (entity_type+entity_id)
- ``POST   /api/annotations``                   新建笔记 (C2: +quote 引文, B+ 锚点)
- ``GET    /api/annotations/{annotation_id}``   查看某条笔记
- ``PUT    /api/annotations/{annotation_id}``   更新笔记
- ``DELETE /api/annotations/{annotation_id}``   删除笔记

C2 (DEV-0190, B+ 锚点): POST/PUT 支持 ``quote`` (高亮原文引文 ≤500 字, migration 118)。
渲染端按「快路径 → 窗内重锚 → 全文兜底 → stale」四步解析抗 wiki 正文漂移。
create/delete 写 audit_log (annotation.*), 失败不阻塞主操作。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.annotation_service import (
    create_annotation,
    delete_annotation,
    get_annotation,
    list_annotations,
    update_annotation,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


class AnnotationCreate(BaseModel):
    """新建笔记请求体。"""

    entity_type: str = Field(..., min_length=1, max_length=64)
    entity_id: str = Field(..., min_length=1, max_length=256)
    content: str = Field(..., min_length=1, max_length=10000)
    range_start: int | None = Field(None, ge=0)
    range_end: int | None = Field(None, ge=0)
    quote: str | None = Field(None, max_length=500)


class AnnotationUpdate(BaseModel):
    """更新笔记请求体 (所有字段可选)。"""

    content: str | None = Field(None, min_length=1, max_length=10000)
    range_start: int | None = Field(None, ge=0)
    range_end: int | None = Field(None, ge=0)
    quote: str | None = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _list(entity_type: str, entity_id: str) -> dict:
    items = list_annotations(entity_type, entity_id)
    return {"version": API_VERSION, "count": len(items), "items": items}


def _create(req: AnnotationCreate) -> dict:
    try:
        item = create_annotation(
            req.entity_type, req.entity_id, req.content,
            req.range_start, req.range_end, req.quote,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    _audit("annotation.create", f"{req.entity_type}/{req.entity_id}",
           {"annotation_id": item.get("id"), "has_quote": req.quote is not None})
    return {"version": API_VERSION, "item": item}


def _get(annotation_id: str) -> dict:
    item = get_annotation(annotation_id)
    if item is None:
        raise HTTPException(status_code=404, detail={"message": f"笔记 {annotation_id!r} 不存在"})
    return {"version": API_VERSION, "item": item}


def _update(annotation_id: str, req: AnnotationUpdate) -> dict:
    try:
        item = update_annotation(
            annotation_id, req.content, req.range_start, req.range_end, req.quote
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    if item is None:
        raise HTTPException(status_code=404, detail={"message": f"笔记 {annotation_id!r} 不存在"})
    return {"version": API_VERSION, "item": item}


def _delete(annotation_id: str) -> dict:
    n = delete_annotation(annotation_id)
    if n == 0:
        raise HTTPException(status_code=404, detail={"message": f"笔记 {annotation_id!r} 不存在"})
    _audit("annotation.delete", annotation_id, None)
    return {"version": API_VERSION, "deleted": annotation_id}


def _audit(action: str, target: str, detail: dict | None) -> None:
    """批注写操作审计 — 失败不阻塞主操作 (与 interest_api 同款兜底)。"""
    try:
        from backend.observability_records import record_audit

        record_audit(actor="web", action=action, target=target, detail=detail)
    except Exception as e:
        from backend.logging_config import logger

        logger.warning(f"annotation audit failed ({action}): {e}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("")
async def list_annotations_endpoint(
    entity_type: str = Query(..., description="被标注对象类型"),
    entity_id: str = Query(..., description="被标注对象 ID"),
):
    """列出某对象的全部笔记。"""
    return await asyncio.to_thread(_list, entity_type, entity_id)


@router.post("", status_code=201)
async def create_annotation_endpoint(req: AnnotationCreate):
    """新建笔记 (验收 3: 笔记 CRUD)。"""
    return await asyncio.to_thread(_create, req)


@router.get("/{annotation_id}")
async def get_annotation_endpoint(annotation_id: str):
    return await asyncio.to_thread(_get, annotation_id)


@router.put("/{annotation_id}")
async def update_annotation_endpoint(annotation_id: str, req: AnnotationUpdate):
    return await asyncio.to_thread(_update, annotation_id, req)


@router.delete("/{annotation_id}")
async def delete_annotation_endpoint(annotation_id: str):
    return await asyncio.to_thread(_delete, annotation_id)


__all__ = ["router"]

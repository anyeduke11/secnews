"""v1.7 Phase 2 — Annotations API (笔记空间)。

路由清单
--------
- ``GET    /api/annotations``                   列出某对象的笔记 (entity_type+entity_id)
- ``POST   /api/annotations``                   新建笔记
- ``GET    /api/annotations/{annotation_id}``   查看某条笔记
- ``PUT    /api/annotations/{annotation_id}``   更新笔记
- ``DELETE /api/annotations/{annotation_id}``   删除笔记
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.annotation_service import (
    create_annotation,
    delete_annotation,
    get_annotation,
    list_annotations,
    update_annotation,
)

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


class AnnotationCreate(BaseModel):
    """新建笔记请求体。"""

    entity_type: str = Field(..., min_length=1, max_length=64)
    entity_id: str = Field(..., min_length=1, max_length=256)
    content: str = Field(..., min_length=1, max_length=10000)
    range_start: Optional[int] = Field(None, ge=0)
    range_end: Optional[int] = Field(None, ge=0)


class AnnotationUpdate(BaseModel):
    """更新笔记请求体 (所有字段可选)。"""

    content: Optional[str] = Field(None, min_length=1, max_length=10000)
    range_start: Optional[int] = Field(None, ge=0)
    range_end: Optional[int] = Field(None, ge=0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _list(entity_type: str, entity_id: str) -> dict:
    items = list_annotations(entity_type, entity_id)
    return {"version": "1.7.0", "count": len(items), "items": items}


def _create(req: AnnotationCreate) -> dict:
    try:
        item = create_annotation(
            req.entity_type, req.entity_id, req.content,
            req.range_start, req.range_end,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    return {"version": "1.7.0", "item": item}


def _get(annotation_id: str) -> dict:
    item = get_annotation(annotation_id)
    if item is None:
        raise HTTPException(status_code=404, detail={"message": f"笔记 {annotation_id!r} 不存在"})
    return {"version": "1.7.0", "item": item}


def _update(annotation_id: str, req: AnnotationUpdate) -> dict:
    try:
        item = update_annotation(
            annotation_id, req.content, req.range_start, req.range_end
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    if item is None:
        raise HTTPException(status_code=404, detail={"message": f"笔记 {annotation_id!r} 不存在"})
    return {"version": "1.7.0", "item": item}


def _delete(annotation_id: str) -> dict:
    n = delete_annotation(annotation_id)
    if n == 0:
        raise HTTPException(status_code=404, detail={"message": f"笔记 {annotation_id!r} 不存在"})
    return {"version": "1.7.0", "deleted": annotation_id}


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

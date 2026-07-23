"""v1.7 Phase 1 — Tags API.

路由清单
--------
- ``GET    /api/tags``           列表（支持 type / parent_id 筛选）
- ``GET    /api/tags/suggest``   按前缀搜索标签
- ``POST   /api/tags``           新建标签
- ``DELETE /api/tags/{tag_id}``  删除标签
- ``GET    /api/tags/by-hotspot/{hotspot_id}``  列出某热点的全部标签

设计
----
- 读/写均通过 ``TagRepository`` (thread-local SQLite 连接, autocommit)。
- 所有同步 DB 操作放 ``asyncio.to_thread`` 避免阻塞 event loop, 与其他
  router (favorites/hotspots) 保持一致。
- 返回结构统一 ``{"version": "1.7.0", ...}``, 与项目其他 API 口径一致。
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.repository.tags_repo import Tag, TagRepository

router = APIRouter(prefix="/api/tags", tags=["tags"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class TagCreate(BaseModel):
    """新建标签请求体。"""

    id: str = Field(..., min_length=1, max_length=128, description="标签唯一 ID")
    label: str = Field(..., min_length=1, max_length=200, description="标签显示名")
    type: str = Field(
        ...,
        pattern="^(domain|category|framework|technique|source|cve)$",
        description="标签类型",
    )
    parent_id: Optional[str] = Field(None, description="父标签 ID (层级)")
    weight: float = Field(1.0, ge=0.0, le=2.0, description="权重 0-2")


# ---------------------------------------------------------------------------
# Helpers (run in thread pool)
# ---------------------------------------------------------------------------
def _tag_to_dict(t: Tag) -> dict:
    return {
        "id": t.id,
        "label": t.label,
        "type": t.type,
        "parent_id": t.parent_id,
        "weight": t.weight,
        "created_at": t.created_at,
    }


def _list_tags(type_: Optional[str], parent_id: Optional[str], limit: int) -> dict:
    repo = TagRepository()
    items = repo.list(type=type_, parent_id=parent_id, limit=limit)
    return {"version": "1.7.0", "count": len(items), "items": [_tag_to_dict(i) for i in items]}


def _suggest_tags(q: str, limit: int) -> dict:
    repo = TagRepository()
    items = repo.suggest(q, limit=limit)
    return {"version": "1.7.0", "count": len(items), "items": [_tag_to_dict(i) for i in items]}


def _create_tag(req: TagCreate) -> dict:
    repo = TagRepository()
    item = repo.add(req.id, req.label, req.type, req.parent_id, req.weight)
    return {"version": "1.7.0", "item": _tag_to_dict(item)}


def _delete_tag(tag_id: str) -> dict:
    repo = TagRepository()
    ok = repo.delete(tag_id)
    if not ok:
        raise HTTPException(status_code=404, detail={"message": f"标签 {tag_id!r} 不存在"})
    return {"version": "1.7.0", "deleted": tag_id}


def _list_by_hotspot(hotspot_id: str) -> dict:
    repo = TagRepository()
    items = repo.list_by_hotspot(hotspot_id)
    return {
        "version": "1.7.0",
        "hotspot_id": hotspot_id,
        "count": len(items),
        "items": [_tag_to_dict(i) for i in items],
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("")
async def list_tags(
    type: Optional[str] = Query(None, description="按类型筛选"),
    parent_id: Optional[str] = Query(None, description="按父标签筛选"),
    limit: int = Query(200, ge=1, le=1000, description="最多返回条数"),
):
    """列出标签（支持 type / parent_id 筛选）。"""
    return await asyncio.to_thread(_list_tags, type, parent_id, limit)


@router.get("/suggest")
async def suggest_tags(
    q: str = Query(..., min_length=1, description="搜索前缀"),
    limit: int = Query(10, ge=1, le=50, description="最多返回条数"),
):
    """按前缀搜索标签 (label LIKE 'q%')。"""
    return await asyncio.to_thread(_suggest_tags, q, limit)


@router.post("", status_code=201)
async def create_tag(req: TagCreate):
    """新建标签。id 已存在则覆盖更新。"""
    return await asyncio.to_thread(_create_tag, req)


@router.delete("/{tag_id}")
async def delete_tag(tag_id: str):
    """删除标签。不存在返回 404。"""
    return await asyncio.to_thread(_delete_tag, tag_id)


@router.get("/by-hotspot/{hotspot_id}")
async def tags_by_hotspot(hotspot_id: str):
    """列出某热点的全部标签 (v1.7 Phase 1 验收 1: 详情页显示标签)。"""
    return await asyncio.to_thread(_list_by_hotspot, hotspot_id)


__all__ = ["router"]

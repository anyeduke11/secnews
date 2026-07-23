"""v1.7 Phase 2 — TechStack REST API.

端点:
- GET    /api/tech-stack                 列表 (可选 ?category=)
- POST   /api/tech-stack                 新建
- GET    /api/tech-stack/{tech_id}       查看
- PUT    /api/tech-stack/{tech_id}       更新
- DELETE /api/tech-stack/{tech_id}       删除
- GET    /api/tech-stack/impact          影响分析 (?article_id=...)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services import tech_stack_service as svc

router = APIRouter(prefix="/api/tech-stack", tags=["tech-stack"])


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
class TechCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=128)
    category: str = Field("", max_length=64)
    proficiency: int = Field(1, ge=1, le=5)
    notes: str = Field("", max_length=2000)


class TechUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    category: Optional[str] = Field(None, max_length=64)
    proficiency: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = Field(None, max_length=2000)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.get("")
async def list_tech_stack(category: Optional[str] = Query(None)):
    items = svc.list_tech(category)
    return {"version": "1.7.0", "count": len(items), "items": items}


@router.post("", status_code=201)
async def create_tech_stack(req: TechCreate):
    item = svc.create_tech(req.id, req.name, req.category, req.proficiency, req.notes)
    return {"version": "1.7.0", "item": item}


@router.get("/impact")
async def impact(article_id: str = Query(..., min_length=1)):
    result = svc.analyze_impact(article_id)
    return {"version": "1.7.0", **result}


@router.get("/{tech_id}")
async def get_tech_stack(tech_id: str):
    item = svc.get_tech(tech_id)
    if not item:
        raise HTTPException(status_code=404, detail="tech_stack 不存在")
    return {"version": "1.7.0", "item": item}


@router.put("/{tech_id}")
async def update_tech_stack(tech_id: str, req: TechUpdate):
    item = svc.update_tech(
        tech_id,
        name=req.name,
        category=req.category,
        proficiency=req.proficiency,
        notes=req.notes,
    )
    if not item:
        raise HTTPException(status_code=404, detail="tech_stack 不存在")
    return {"version": "1.7.0", "item": item}


@router.delete("/{tech_id}")
async def delete_tech_stack(tech_id: str):
    deleted = svc.delete_tech(tech_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="tech_stack 不存在")
    return {"version": "1.7.0", "deleted": deleted}

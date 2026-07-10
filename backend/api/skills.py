"""Phase 41 Skill 管理 API 端点。

路由清单
--------
- ``GET    /api/skills``                列表 + source/tag/keyword 筛选
- ``GET    /api/skills/count_by_source``按 source 统计 (筛选 tab 徽标)
- ``POST   /api/skills``                新增
- ``PATCH  /api/skills/{id}``           部分更新
- ``DELETE /api/skills/{id}``           删除

设计原则
--------
- 同步 DB 操作通过 ``asyncio.to_thread`` 包装, 避免阻塞 event loop
- 复制 install_command 走前端 Clipboard API, 后端不返回明文到日志
- 400/404/500 用 HotspotException 体系, 中文 message
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from backend.logging_config import logger
from backend.repository.skills_repo import VALID_SOURCES, SkillRepository

router = APIRouter(prefix="/api/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class AddSkillRequest(BaseModel):
    name: str = Field(..., max_length=200, description="skill 名称 (必填)")
    url: str = Field(..., max_length=500, description="skill 链接 (必填)")
    install_command: str = Field(..., description="安装指令 (必填, 一键复制内容)")
    description: Optional[str] = Field(None, description="简介")
    source: str = Field("manual", description="npx/uvx/curl/git/manual")
    tags: list[str] = Field(default_factory=list, description="标签数组")


class PatchSkillRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    url: Optional[str] = Field(None, max_length=500)
    install_command: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("")
async def list_skills(
    source: Optional[str] = Query(None, description="按 source 筛选"),
    tag: Optional[str] = Query(None, description="按 tag 筛选 (单 tag)"),
    keyword: Optional[str] = Query(None, description="name/description 关键词搜索"),
    limit: int = Query(200, ge=1, le=1000),
):
    """多维筛选 skills。排序: created_at DESC。"""
    if source and source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail={"message": f"source 必须为 {', '.join(VALID_SOURCES)}; got {source!r}"},
        )
    repo = SkillRepository()
    try:
        items, total = await asyncio.to_thread(
            repo.list, source=source, tag=tag, keyword=keyword, limit=limit
        )
    except Exception as e:
        logger.error(f"list skills failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"列表失败: {e}"})

    return {
        "version": "1.2.0",
        "total": total,
        "items": [it.to_dict() for it in items],
    }


@router.get("/count_by_source")
async def count_by_source():
    """按 source 分组统计 (用于筛选 tab 徽标)。"""
    repo = SkillRepository()
    try:
        counts = await asyncio.to_thread(repo.count_by_source)
    except Exception as e:
        logger.error(f"count_by_source failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"统计失败: {e}"})
    return {
        "version": "1.2.0",
        "counts": counts,
    }


@router.post("", status_code=201)
async def add_skill(req: AddSkillRequest):
    """新增 skill。"""
    if req.source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail={"message": f"source 必须为 {', '.join(VALID_SOURCES)}; got {req.source!r}"},
        )
    repo = SkillRepository()
    try:
        item = await asyncio.to_thread(
            repo.add,
            name=req.name,
            url=req.url,
            install_command=req.install_command,
            description=req.description,
            source=req.source,
            tags=req.tags or [],
        )
    except Exception as e:
        msg = str(e)
        if "不能为空" in msg:
            raise HTTPException(status_code=400, detail={"message": msg})
        logger.error(f"add skill failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"添加失败: {e}"})
    return {
        "version": "1.2.0",
        "item": item.to_dict(),
    }


@router.patch("/{skill_id}")
async def patch_skill(skill_id: int, req: PatchSkillRequest):
    """部分更新 skill; 未传字段保持原值。"""
    if req.source is not None and req.source not in VALID_SOURCES:
        raise HTTPException(
            status_code=400,
            detail={"message": f"source 必须为 {', '.join(VALID_SOURCES)}; got {req.source!r}"},
        )
    repo = SkillRepository()
    try:
        item = await asyncio.to_thread(
            repo.update,
            int(skill_id),
            name=req.name,
            url=req.url,
            install_command=req.install_command,
            description=req.description,
            source=req.source,
            tags=req.tags,
        )
    except Exception as e:
        msg = str(e)
        if "不存在" in msg or "not found" in msg.lower():
            raise HTTPException(status_code=404, detail={"message": f"skill {skill_id} 不存在"})
        if "不能为空" in msg:
            raise HTTPException(status_code=400, detail={"message": msg})
        logger.error(f"update skill failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"更新失败: {e}"})
    return {
        "version": "1.2.0",
        "item": item.to_dict(),
    }


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: int):
    """硬删除 skill。204 (idempotent)。"""
    repo = SkillRepository()
    try:
        await asyncio.to_thread(repo.delete, int(skill_id))
    except Exception as e:
        logger.error(f"delete skill failed: {e}")
        raise HTTPException(status_code=500, detail={"message": f"删除失败: {e}"})
    return Response(status_code=204)


__all__ = ["router"]

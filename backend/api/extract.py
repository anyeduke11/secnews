"""v1.7 Phase 1 — Extract API.

路由清单
--------
- ``POST /api/extract/preview``                 预览: 给定文本返回提取的标签 (不持久化)
- ``POST /api/extract/hotspot/{hotspot_id}``    对热点触发自动提取 (attach + 返回)
- ``POST /api/extract/knowledge/{item_id}``     对知识条目触发提取 (写 tags + 推进 lifecycle)

设计
----
- Phase 1 采用**同步提取**: 调用 ``extract_service.extract_and_attach`` 直接
  关联标签到 ``hotspot_tags`` 表, 立即返回结果。PRD §4.2 的 pending/confirm
  审核队列推迟到 Phase 2 (需要 kv_cache 持久化 + 人工确认 UI), Phase 1 验收 1
  仅要求"热点打开后显示自动提取的标签", 同步提取已满足。
- 知识条目: 提取后将 tag id 写入 ``knowledge_items.tags`` (JSON), 并通过
  ``sag_service.transition`` 把 lifecycle 从 signal 推进到 amplify:tagged。
- 所有同步 DB 操作放 ``asyncio.to_thread``。
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.knowledge_repo import knowledge_repo
from backend.repository.tags_repo import TagRepository
from backend.services.extract_service import extract_and_attach, extract_tags

router = APIRouter(prefix="/api/extract", tags=["extract"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ExtractPreviewRequest(BaseModel):
    """预览提取: 给定文本/标题/分类, 返回标签建议 (不持久化)。"""

    text: str = Field("", description="正文文本")
    title: str = Field("", description="标题")
    category: str = Field("", description="分类 (ai/security/finance/...)")


# ---------------------------------------------------------------------------
# Helpers (run in thread pool)
# ---------------------------------------------------------------------------
def _preview(req: ExtractPreviewRequest) -> dict:
    tags = extract_tags(req.text, title=req.title, category=req.category)
    return {"version": "1.7.0", "count": len(tags), "items": tags}


def _extract_hotspot(hotspot_id: str) -> dict:
    item = HotspotRepository().get_by_id(hotspot_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"热点 {hotspot_id!r} 不存在"},
        )
    text = " ".join(filter(None, [item.title, item.summary]))
    extracted = extract_and_attach(
        hotspot_id,
        text=text,
        title=item.title,
        category=item.category.value,
    )
    attached = TagRepository().list_by_hotspot(hotspot_id)
    return {
        "version": "1.7.0",
        "hotspot_id": hotspot_id,
        "extracted": extracted,
        "attached": [
            {"id": t.id, "label": t.label, "type": t.type} for t in attached
        ],
    }


def _extract_knowledge(item_id: str) -> dict:
    item = knowledge_repo.get_item(item_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"知识条目 {item_id!r} 不存在"},
        )
    # 知识条目正文在 .md 文件里, SQLite 只存元数据; Phase 1 用 title+topic 提取
    text = " ".join(filter(None, [item.title, item.topic or ""]))
    extracted = extract_tags(text, title=item.title, category=item.domain or "")
    # 把提取到的 tag id 合并进 knowledge_items.tags (去重保序)
    existing = list(item.tags)
    for t in extracted:
        if t["tag_id"] not in existing:
            existing.append(t["tag_id"])
    item.tags = existing
    # 推进 lifecycle: signal -> amplify:tagged (仅在更早期状态时推进)
    if item.lifecycle in ("signal",):
        item.lifecycle = "amplify:tagged"
    knowledge_repo.upsert_item(item)
    # 回写 .md (非关键, 失败不阻塞)
    try:
        from backend.services.knowledge_sync import write_item_to_md
        write_item_to_md(item.to_dict())
    except Exception:
        pass
    return {
        "version": "1.7.0",
        "item_id": item_id,
        "extracted": extracted,
        "tags": item.tags,
        "lifecycle": item.lifecycle,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/preview")
async def preview_extract(req: ExtractPreviewRequest):
    """预览标签提取 (不持久化)。用于前端 TagSelector 调试/展示。"""
    return await asyncio.to_thread(_preview, req)


@router.post("/hotspot/{hotspot_id}", status_code=200)
async def extract_hotspot(hotspot_id: str):
    """对热点触发自动标签提取 (v1.7 Phase 1 验收 1)。

    读取热点 title+summary, 调用三层提取器, 把命中的标签关联到 hotspot_tags 表。
    """
    return await asyncio.to_thread(_extract_hotspot, hotspot_id)


@router.post("/knowledge/{item_id}", status_code=200)
async def extract_knowledge(item_id: str):
    """对知识条目触发提取, 写入 tags 并推进 SAG lifecycle。"""
    return await asyncio.to_thread(_extract_knowledge, item_id)


__all__ = ["router"]

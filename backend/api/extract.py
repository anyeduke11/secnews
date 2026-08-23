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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.events import publish_event
from backend.repository.hotspot_repo import HotspotRepository
from backend.repository.knowledge_repo import knowledge_repo
from backend.repository.tags_repo import TagRepository
from backend.services.extract_service import extract_and_attach, extract_tags
from backend.version import APP_VERSION as API_VERSION

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
    return {"version": API_VERSION, "count": len(tags), "items": tags}


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
        "version": API_VERSION,
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
    # 推进 lifecycle: kl:raw -> kl:refine (P1-3 统一为 KL 规范; P1.5 单轨化)
    if item.lifecycle in ("kl:raw", None):
        item.lifecycle = "kl:refine"
    knowledge_repo.upsert_item(item)
    # 回写 .md (非关键, 失败不阻塞)
    try:
        from backend.services import ai_hub
        ai_hub.write_item(item.to_dict(), agent="api:extract")
    except Exception:
        pass
    return {
        "version": API_VERSION,
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

    v0.5 M2-Task5: 完成后推送 ``extract_done`` SSE 事件 (SPEC §6.2 契约:
    payload = {item_id, tags:[], lifecycle}; hotspot 路径无 lifecycle 概念,
    传 None 占位, 前端可用 item_id 推断 hotspot 域)。
    """
    result = await asyncio.to_thread(_extract_hotspot, hotspot_id)
    try:
        await publish_event("extract_done", {
            "item_id": hotspot_id,
            "tags": [t.get("label", t.get("id")) for t in result.get("attached", [])],
            "lifecycle": None,  # hotspot 路径不推进 lifecycle, 仅作占位
        })
    except Exception:
        pass  # SSE 推送失败不阻塞主流程
    return result


@router.post("/knowledge/{item_id}", status_code=200)
async def extract_knowledge(item_id: str):
    """对知识条目触发提取, 写入 tags 并推进 SAG lifecycle。

    v0.5 M2-Task5: 完成后推送 ``extract_done`` 事件, payload 含完整
    {item_id, tags, lifecycle}, 供前端 KnowledgeProcessingView 实时刷新。
    """
    result = await asyncio.to_thread(_extract_knowledge, item_id)
    try:
        await publish_event("extract_done", {
            "item_id": item_id,
            "tags": [t.get("label", t.get("tag_id")) for t in result.get("extracted", [])],
            "lifecycle": result.get("lifecycle"),
        })
    except Exception:
        pass
    return result


__all__ = ["router"]

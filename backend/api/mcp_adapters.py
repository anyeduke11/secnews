"""v1.7 Phase 7 — MCP Server 适配层.

为 fastapi-mcp 不能直接路由到的端点 (spec §4 列出的 13 个 MCP tool 部分
没有 1:1 对应的 FastAPI 路由), 在此提供 3 个适配端点:

- ``GET  /api/profile``         → get_personal_profile
- ``POST /api/cubox/sync``      → trigger_cubox_sync
- ``POST /api/extract/auto``    → trigger_extract_tags (body hotspot_id)

其余 10 个 MCP tool 直接 1:1 复用既有 FastAPI 路由 (见 mcp_config.py)。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.repository.profile_repo import ProfileRepository
from backend.version import APP_VERSION as API_VERSION

log = logging.getLogger("hotspot.api.mcp_adapters")

router = APIRouter(prefix="/api", tags=["mcp-adapters"])


# ---------------------------------------------------------------------------
# /api/profile — get_personal_profile
# ---------------------------------------------------------------------------
@router.get("/profile")
async def get_personal_profile(
    limit: int = Query(50, ge=1, le=200, description="最多返回维度数"),
):
    """返回个人画像 (EMA 权重 + 兴趣分布)。

    - 来源: profile_repo 读 personal_profile 表
    - 同步直返, 无 LLM
    """
    def _read() -> dict:
        repo = ProfileRepository()
        all_rows = repo.list_all() if hasattr(repo, "list_all") else []
        # 按 weight 绝对值排序
        rows = sorted(
            all_rows,
            key=lambda r: abs(float(r.get("weight", 0))),
            reverse=True,
        )[:limit]
        return {
            "version": API_VERSION,
            "total": len(all_rows),
            "profile": [
                {
                    "key": r.get("key", ""),
                    "weight": float(r.get("weight", 0)),
                    "signals": int(r.get("signals", 0)),
                    "updated_at": r.get("updated_at", ""),
                }
                for r in rows
            ],
        }

    try:
        return await asyncio.to_thread(_read)
    except Exception as e:
        log.error(f"get_personal_profile failed: {e}")
        raise HTTPException(status_code=500, detail={"message": str(e)})


# ---------------------------------------------------------------------------
# /api/cubox/sync — trigger_cubox_sync
# ---------------------------------------------------------------------------
class CuboxSyncRequest(BaseModel):
    """cubox-cli 同步请求。"""

    target_path: str = Field("", description="目标目录; 空=默认 knowledge/items/")
    format: str = Field("md", description="md | json")
    limit: int = Field(100, ge=1, le=1000, description="最多同步卡片数")


@router.post("/cubox/sync")
async def trigger_cubox_sync(req: CuboxSyncRequest):
    """调用 cubox-cli 本地同步卡片到 knowledge/items/。

    - 不调 LLM
    - 失败返回 500 + error message
    """
    from backend.services.cubox_sync import sync_cubox_to_knowledge  # type: ignore

    def _run() -> dict:
        try:
            result = sync_cubox_to_knowledge(  # type: ignore[call-arg]
                target_path=req.target_path or None,
                format=req.format,
                limit=req.limit,
            )
            return {"version": API_VERSION, "success": True, "result": result}
        except Exception as e:
            return {"version": API_VERSION, "success": False, "error": str(e)}

    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        log.error(f"trigger_cubox_sync failed: {e}")
        raise HTTPException(status_code=500, detail={"message": str(e)})


# ---------------------------------------------------------------------------
# /api/extract/auto — trigger_extract_tags (body 形式 hotspot_id)
# ---------------------------------------------------------------------------
class ExtractAutoRequest(BaseModel):
    """按 hotspot_id 触发标签提取。"""

    hotspot_id: str = Field(..., min_length=1, description="hotspot ID")


@router.post("/extract/auto")
async def trigger_extract_tags(req: ExtractAutoRequest):
    """对单条 hotspot 触发本地规则提取 + attach 标签。

    - 复用 ``extract_and_attach`` 同步直返
    - 不调 LLM
    """
    from backend.services.extract_service import extract_and_attach
    from backend.repository.hotspot_repo import HotspotRepository
    from backend.repository.tags_repo import TagRepository

    def _run() -> dict:
        item = HotspotRepository().get_by_id(req.hotspot_id)
        if item is None:
            raise HTTPException(
                status_code=404,
                detail={"message": f"hotspot {req.hotspot_id!r} 不存在"},
            )
        text = " ".join(filter(None, [item.title, item.summary]))
        extracted = extract_and_attach(
            req.hotspot_id,
            text=text,
            title=item.title,
            category=item.category.value if hasattr(item.category, "value") else str(item.category),
        )
        attached = TagRepository().list_by_hotspot(req.hotspot_id)
        return {
            "version": API_VERSION,
            "success": True,
            "hotspot_id": req.hotspot_id,
            "extracted_count": len(extracted) if isinstance(extracted, list) else 0,
            "tags": [
                {"id": t.id, "label": t.label, "type": t.type} for t in attached
            ],
        }

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"trigger_extract_tags failed: {e}")
        raise HTTPException(status_code=500, detail={"message": str(e)})


# ---------------------------------------------------------------------------
# /api/favorites/by-hotspot — MCP 友好入口 (输入仅 hotspot_id, 内部查表)
# ---------------------------------------------------------------------------
class AddFavoriteByHotspotRequest(BaseModel):
    """通过 hotspot_id 收藏 (MCP tool add_favorite 用)。

    行为: 查 hotspots 表 → 拿到 category/title/source/url → 调 favorite_repo.add(created_via='mcp')。
    若 hotspot_id 不存在 → 404。
    可选 note → 同步创建 annotation。
    """

    hotspot_id: str = Field(..., min_length=1)
    note: str = Field("", description="可选备注, 若非空则同步创建 annotation")


@router.post("/favorites/by-hotspot")
async def add_favorite_by_hotspot(req: AddFavoriteByHotspotRequest):
    """MCP tool add_favorite 适配入口: 仅需 hotspot_id (其余字段从 hotspots 表查)。"""
    from backend.repository.hotspot_repo import HotspotRepository
    from backend.repository.favorite_repo import FavoriteRepository

    def _run() -> dict:
        item = HotspotRepository().get_by_id(req.hotspot_id)
        if item is None:
            raise HTTPException(
                status_code=404,
                detail={"message": f"hotspot {req.hotspot_id!r} 不存在"},
            )
        # 提取字段
        cat = item.category.value if hasattr(item.category, "value") else str(item.category)
        repo = FavoriteRepository()
        created, fav = repo.add(
            hotspot_id=req.hotspot_id.strip(),
            category=cat,
            title=item.title or "",
            source=item.source or "",
            url=item.url or "",
            created_via="mcp",
        )
        result = {
            "version": API_VERSION,
            "success": True,
            "created": created,
            "item_id": fav.id,
            "hotspot_id": fav.hotspot_id,
            "created_via": fav.created_via,
        }
        # 可选: 同步创建 annotation
        if req.note:
            try:
                from backend.repository.annotation_repo import AnnotationRepository
                AnnotationRepository().create(
                    entity_type="hotspot",
                    entity_id=req.hotspot_id,
                    content=req.note,
                    source="mcp",
                )
                result["note_annotation_id"] = True
            except Exception as e:
                log.warning(f"add_favorite_by_hotspot: note annotation failed: {e}")
        return result

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"add_favorite_by_hotspot failed: {e}")
        raise HTTPException(status_code=500, detail={"message": str(e)})


__all__ = ["router"]

"""Phase 4 /api/export router — 预生成 HTML + ETag 304。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Header, Response

from backend.logging_config import logger
from backend.services.export_service import (
    get_cached_etag,
    get_or_build_html,
)

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("")
async def export(
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
):
    """返回预生成的静态 HTML；客户端传 If-None-Match 触发 304。

    Phase 9 修复：cache miss 时同步 DB query + 文件 IO 放 thread pool。
    """
    etag = get_cached_etag() or '"no-cache"'
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers={"ETag": etag})
    html, fresh_etag = await asyncio.to_thread(get_or_build_html)
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={
            "ETag": fresh_etag,
            "Cache-Control": "public, max-age=1800",
        },
    )


@router.post("/rebuild")
async def export_rebuild():
    """强制重建（运维用）。

    Phase 9 修复：同步 DB query + 文件 IO 放 thread pool。
    """
    from backend.services.export_service import rebuild_export_cache

    try:
        etag = await asyncio.to_thread(rebuild_export_cache)
        return {"version": "1.2.0", "etag": etag, "status": "ok"}
    except Exception as e:
        logger.error(f"export rebuild failed: {e}")
        return Response(
            content=f"rebuild failed: {e}",
            status_code=500,
        )

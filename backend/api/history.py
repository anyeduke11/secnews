"""Phase 28 历史资讯 API 端点.

- ``GET  /api/history/batches``                      列出所有有数据的批次(按 batch_no DESC, 不含当前批次)
- ``GET  /api/history/batches/{batch_no}/items``     列出指定批次内的所有 hotspots
- ``GET  /api/history/batches/{batch_no}/summary``   批次统计摘要(分类分布 + Top5 信源)
- ``POST /api/history/archive``                      归档热点 + 触发 knowledge 同步
"""
from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.config import config
from backend.domain.enums import Category
from backend.exceptions import InvalidParamException
from backend.logging_config import logger
from backend.services.batch_service import (
    BatchService,
    get_batch_range,
)

router = APIRouter(prefix="/api/history", tags=["history"])
_service = BatchService()


def _build_items_payload(
    batch_no: int,
    category: str,
    keyword: str,
    cursor: Optional[str],
    limit: int,
) -> dict[str, Any]:
    """同步获取批次内 items 列表(在 thread pool 中执行)."""
    # category 校验
    if category != "all" and category not in {c.value for c in Category}:
        raise InvalidParamException(
            f"category must be one of all, {','.join(c.value for c in Category)}; got {category!r}"
        )
    return _service.get_batch_items(
        batch_no=batch_no,
        category=category,
        keyword=keyword,
        cursor=cursor,
        limit=limit,
    )


@router.get("/batches")
async def list_batches(
    cursor: Optional[int] = Query(None, description="上次返回的最小 batch_no; 首次传 None"),
    limit: int = Query(50, ge=1, le=200, description="每页批次数"),
):
    """列出所有历史批次(按 batch_no DESC, 不含当前批次).

    Returns
    -------
    {
      "batches": [{batch_no, start, end, item_count, favorite_count}, ...],
      "total": int,                  # 本页所有 batch 的 item_count 总和
      "next_cursor": int or null,    # 下一页的 cursor
      "has_more": bool
    }
    """
    return await asyncio.to_thread(_service.list_batches, cursor, limit)


@router.get("/batches/{batch_no}/items")
async def get_batch_items(
    batch_no: int,
    category: str = Query("all", description="分类筛选, all 或具体值"),
    keyword: str = Query("", description="FTS5 关键词"),
    cursor: str = Query("", description="上次返回的 cursor(base64)"),
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
):
    """列出指定批次内的所有 hotspots.

    复用 list_hotspots 的 cursor 编码格式.
    """
    try:
        result = await asyncio.to_thread(
            _build_items_payload,
            batch_no,
            category,
            keyword,
            cursor or None,
            limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    except InvalidParamException as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    return result


@router.get("/batches/{batch_no}/summary")
async def get_batch_summary(batch_no: int):
    """批次统计摘要: 分类分布 + Top5 信源 + 收藏数."""
    try:
        return await asyncio.to_thread(_service.get_batch_summary, batch_no)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})


@router.get("/batches/{batch_no}/range")
async def get_batch_range_endpoint(batch_no: int):
    """返回批次的 [start, end) 时间区间."""
    try:
        start, end = get_batch_range(batch_no)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    return {
        "batch_no": batch_no,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


# ── Archive ──────────────────────────────────────────────────────


class ArchiveRequest(BaseModel):
    item_ids: list[str]


def _has_archived_column() -> bool:
    """Check if hotspots table has an 'archived' column."""
    try:
        conn = sqlite3.connect(str(config.db_path))
        cursor = conn.execute("PRAGMA table_info(hotspots)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        return "archived" in columns
    except Exception:
        return False


def _archive_hotspots(item_ids: list[str]) -> int:
    """Mark hotspots as archived. Returns count archived.

    If the hotspots table has no 'archived' column, skips SQL and returns 0.
    """
    if not item_ids:
        return 0
    if not _has_archived_column():
        logger.info("hotspots table has no 'archived' column, skipping SQL archive")
        return 0
    try:
        conn = sqlite3.connect(str(config.db_path))
        placeholders = ",".join("?" * len(item_ids))
        cursor = conn.execute(
            f"UPDATE hotspots SET archived = 1 WHERE id IN ({placeholders})",
            item_ids,
        )
        archived = cursor.rowcount
        conn.close()
        return archived
    except Exception as e:
        logger.error(f"archive SQL failed: {e}")
        return 0


@router.post("/archive")
async def archive_items(req: ArchiveRequest):
    """归档热点资讯 + 异步触发 knowledge 同步.

    Body: ``{item_ids: list[str]}`` (hotspots.id 是 TEXT)

    Returns: ``{archived: N, knowledge_synced: M}``
    """
    item_ids = req.item_ids

    # Archive in DB (skips gracefully if no archived column)
    archived = await asyncio.to_thread(_archive_hotspots, item_ids)

    # Async knowledge sync (try/except, don't block main archive flow)
    knowledge_synced = 0
    if item_ids:
        try:
            from backend.services.history_import import import_from_history
            result = await asyncio.to_thread(import_from_history, item_ids)
            knowledge_synced = result.get("imported", 0)
        except Exception as e:
            logger.error(f"knowledge sync after archive failed: {e}")

    return {"archived": archived, "knowledge_synced": knowledge_synced}


__all__ = ["router"]

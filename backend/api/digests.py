"""v1.7 Phase 4 — 简报 API.

端点
----
- ``GET  /api/digests``                 列出简报 (按 created_at DESC)
- ``GET  /api/digests/latest``          最新一条简报 (无则 404)
- ``GET  /api/digests/{digest_id}``     单条简报
- ``POST /api/digests/generate``        手动触发生成昨日简报
- ``PUT  /api/digests/read``            标记简报已读 (写 kv_cache)
- ``DELETE /api/digests/{digest_id}``   删除简报
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.repository.digest_repo import DigestRepository
from backend.services.digest_service import generate_daily_digest, mark_digest_read
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/digests", tags=["digests"])


@router.get("")
async def list_digests(
    period: str | None = Query(None, description="按周期过滤 (daily/weekly)"),
    limit: int = Query(20, ge=1, le=100),
):
    """列出简报, 按 created_at DESC."""
    repo = DigestRepository()
    items = repo.list_by_period(period=period, limit=limit)
    return {"version": API_VERSION, "items": items, "total": len(items)}


@router.get("/latest")
async def get_latest_digest(period: str | None = Query(None)):
    """获取最新一条简报. 无则 404."""
    repo = DigestRepository()
    item = repo.get_latest(period=period)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"message": "暂无简报"},
        )
    return {"version": API_VERSION, "item": item}


@router.get("/{digest_id}")
async def get_digest(digest_id: str):
    """获取单条简报."""
    repo = DigestRepository()
    item = repo.get(digest_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"简报 {digest_id} 不存在"},
        )
    return {"version": API_VERSION, "item": item}


@router.post("/generate")
async def generate_digest(top_n: int = Query(3, ge=1, le=10)):
    """手动触发生成昨日简报.

    正常由 scheduler 每 08:00 Shanghai 自动触发; 此端点供手动补生成.

    v0.6.3 P0-2: 必须 to_thread —— generate_daily_digest 是同步重活
    (DB 扫描 + LLM 调用), 直接在事件循环线程跑会 (a) 阻塞全站请求,
    (b) 其内部的 new_event_loop 桥在运行中的 loop 上必然 RuntimeError
    → LLM 叙事静默缺失。to_thread 后与 08:00 job 路径同构, 叙事恢复。
    """
    import asyncio

    item = await asyncio.to_thread(generate_daily_digest, top_n)
    return {"version": API_VERSION, "item": item}


@router.put("/read")
async def mark_read():
    """标记当前最新简报已读 (写 kv_cache)."""
    mark_digest_read()
    return {"version": API_VERSION, "status": "ok"}


@router.delete("/{digest_id}")
async def delete_digest(digest_id: str):
    """删除简报."""
    repo = DigestRepository()
    ok = repo.delete(digest_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail={"message": f"简报 {digest_id} 不存在"},
        )
    return {"version": API_VERSION, "status": "ok", "deleted": digest_id}


__all__ = ["router"]

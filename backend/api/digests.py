"""v1.7 Phase 4 — 简报 API.

端点
----
- ``GET  /api/digests``                 列出简报 (按 created_at DESC)
- ``GET  /api/digests/latest``          最新一条简报 (无则 404)
- ``GET  /api/digests/{digest_id}``     单条简报
- ``POST /api/digests/generate``        手动触发生成昨日简报
- ``PUT  /api/digests/read``            标记简报已读 (写 kv_cache)
- ``DELETE /api/digests/{digest_id}``   删除简报
- ``GET  /api/digests/priority``        DEV-0177 T0.5 收敛: SK-01 今日重点情报
                                        (实践域分区, 5min TTL 缓存, 优雅降级)
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Query

from backend.repository.digest_repo import DigestRepository
from backend.services.digest_service import generate_daily_digest, mark_digest_read
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/digests", tags=["digests"])

# DEV-0177: SK-01 priority digest TTL 缓存 (compute 可能真调 dsh/ai_hub, 昂贵)
_PRIORITY_TTL_S = 300.0
_priority_cache: dict[str, float | dict] = {"ts": 0.0, "data": {}}


def _priority_service():
    """工厂函数 (测试注入点)."""
    from backend.services.skill_registry.sk01_daily_priority import DailyPriorityIntelService

    return DailyPriorityIntelService()


@router.get("/priority")
async def get_priority_digest(force: bool = Query(False, description="绕过 TTL 缓存强制重算")):
    """SK-01 今日重点情报 (DEV-0177, T0.5 收敛).

    返回 DailyPriorityIntelService.compute(): top_items (含 practice_domain)、
    practice_partitions (有画像=按域分组+other, 无画像=None)、interest_domains、
    mode (dsh / fallback_no_data / fallback_dsh_failed)。

    优雅降级: dsh/ai_hub 不可达或依赖未就绪时返回 fallback mode (HTTP 200),
    前端按 empty 态渲染, 不报错。5min TTL 缓存; ``?force=true`` 强制重算。
    """
    now = time.monotonic()
    cached = _priority_cache["data"]
    ts = float(_priority_cache["ts"])
    if not force and cached and (now - ts) < _PRIORITY_TTL_S:
        return {**cached, "cached": True}

    try:
        result = await asyncio.to_thread(_priority_service().compute)
    except Exception as e:
        from backend.logging_config import logger

        logger.warning(f"priority digest compute failed, degrade: {e}")
        result = {
            "top_items": [],
            "watchlist_changes": [],
            "suggested_actions": [f"优先级摘要暂不可用 ({type(e).__name__})"],
            "generated_at": "",
            "mode": "fallback_error",
            "interest_domains": [],
            "practice_partitions": None,
        }
    _priority_cache["ts"] = time.monotonic()
    _priority_cache["data"] = result
    return {**result, "cached": False}


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

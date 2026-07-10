"""POST /api/refresh — 手动触发完整采集, 同步等待结果.

Phase 32: 修复 "刷新按钮点击后数据没变" 缺陷 — 之前 GET /api/hotspots
只读 DB 缓存, 没触发后端实际采集。本端点用 app.state.scheduler.service
单例同步跑一次 run_once(), 返回 CollectionReport.

防并发: CollectionService 内部 asyncio.Lock, scheduler 周期任务和
手动触发共用同一把锁, 同一时刻只允许一个采集在跑。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from backend.logging_config import logger

router = APIRouter(prefix="/api", tags=["refresh"])
_logger = logger.bind(component="api.refresh")


@router.post("/refresh")
async def manual_refresh(request: Request) -> dict:
    """手动触发一次完整采集, 同步等结果.

    行为
    ----
    - 从 ``app.state.scheduler.service`` 拿 CollectionService 单例
    - 调用 ``await service.run_once()`` 同步等到采集完成
    - 返回 ``CollectionReport`` 的核心字段, 方便前端展示/调试
    - 失败时返回 ``ok=False`` + error, 状态码仍 200 (业务错误, 非 HTTP 错误)
    """
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None or scheduler.service is None:
        _logger.error("service not initialized, manual_refresh skipped")
        return {
            "ok": False,
            "error": "service not initialized",
        }

    try:
        report = await scheduler.service.run_once()
    except Exception as e:
        _logger.error(f"manual_refresh failed: {e}")
        return {
            "ok": False,
            "error": str(e),
        }

    return {
        "ok": True,
        "total": report.total,
        "success_count": report.success_count,
        "failed_count": report.failed_count,
        "fallback_count": report.fallback_count,
        "duration_ms": report.duration_ms,
        "started_at": report.started_at.isoformat() if report.started_at else None,
        "finished_at": report.finished_at.isoformat() if report.finished_at else None,
        "failures": report.failures,
    }


__all__ = ["router"]

"""运行时设置 API — 刷新间隔等热配置端点。

- ``POST /api/settings/refresh-interval`` — 更新采集间隔（分钟）
- ``GET  /api/settings/features`` — 扩展 feature flag（前端 useFeatureFlags 数据源）
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.config import config
from backend.extensions import get_enabled_extensions, is_extension_enabled
from backend.logging_config import logger

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/features")
async def get_features() -> dict:
    """返回全部扩展域的启停状态（feature_gates.toml 派生的运行时视图）。"""
    return {
        "codegarden": is_extension_enabled("codegarden"),
        "codegarden_phase2b": is_extension_enabled("codegarden_phase2b"),
        "mcp": is_extension_enabled("mcp"),
        "sync": is_extension_enabled("sync"),
        "tech_stack": is_extension_enabled("tech_stack"),
        "security_graph": is_extension_enabled("security_graph"),
        "secnews": is_extension_enabled("secnews"),
        "crm": is_extension_enabled("crm"),
        # C4 之后 dsh 才真正可配: 关闭时 /api/dsh/* 返回 404, 界面需如实呈现该状态
        "dsh": is_extension_enabled("dsh"),
        "workbench_ui": config.feature_workbench_ui,
        "enabled_extensions": get_enabled_extensions(),
    }


class RefreshIntervalRequest(BaseModel):
    minutes: int = Field(..., ge=1, le=1440, description="采集间隔（分钟，1-1440）")


@router.post("/refresh-interval")
async def set_refresh_interval(body: RefreshIntervalRequest, request: Request):
    """动态调整 collect_all 采集间隔。

    1. 更新 ``config.collect_interval_seconds``（运行时生效）
    2. 调用 ``scheduler.reschedule()`` 更新 APScheduler 定时器
    """
    interval_seconds = body.minutes * 60

    # 更新 config（运行时生效）
    old = config.collect_interval_seconds
    config.collect_interval_seconds = interval_seconds

    # 更新调度器
    sched = getattr(request.app.state, "scheduler", None)
    if sched is not None:
        try:
            sched.reschedule(interval_seconds)
            logger.info(
                "refresh interval updated: %s min (%ss) -> %s min (%ss)",
                old // 60, old, body.minutes, interval_seconds,
            )
        except Exception as e:
            logger.warning(f"reschedule failed (ignored): {e}")
            return {
                "status": "degraded",
                "message": f"config updated but scheduler reschedule failed: {e}",
                "interval_minutes": body.minutes,
                "interval_seconds": interval_seconds,
            }

    return {
        "status": "ok",
        "message": f"采集间隔已更新为 {body.minutes} 分钟",
        "interval_minutes": body.minutes,
        "interval_seconds": interval_seconds,
    }
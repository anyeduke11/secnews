"""MCP 设置 API (ungated 基础设施, 2026-09-22 设置重构 P2)。

路由清单
--------
- ``GET /api/settings/mcp/config``    stdio/SSE 配置 (依赖 server 本体, feature_mcp=false 时 404)
- ``PUT /api/settings/mcp/enabled``   切换 feature.mcp_server — 立即生效 + settings kv 持久化

背景: 原两端点住在 gated mcp.py (extensions.mcp TOML 默认 false → 404),
UI 永远无法开启 MCP 的自锁; toggle 且只改进程内单例重启即丢。本文件双修。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import config
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/settings", tags=["mcp-settings"])


class ToggleEnabledRequest(BaseModel):
    enabled: bool = Field(..., description="true=启用, false=停用 MCP server")


def _toggle(enabled: bool) -> dict:
    from backend.services.feature_flag_service import disable, enable

    ok = enable("mcp") if enabled else disable("mcp")
    if not ok:
        raise HTTPException(status_code=400, detail={"message": "未知 feature flag: mcp"})
    return {
        "version": API_VERSION,
        "enabled": enabled,
        "applied": ok,
        "persisted": True,
        "note": "MCP server 开关已立即生效并持久化; /api/mcp/* 调试路由随 extensions.mcp TOML gate 下次启动生效",
    }


@router.get("/mcp/config")
async def get_mcp_config():
    """MCP 端点 + AI Agent settings.json 示例 (server 本体关闭时 404)。"""
    from backend.api.mcp import build_mcp_config_payload

    if not config.feature_mcp:
        raise HTTPException(status_code=404, detail={"message": "MCP server is disabled"})
    return await asyncio.to_thread(build_mcp_config_payload)


@router.put("/mcp/enabled")
async def toggle_mcp_enabled(req: ToggleEnabledRequest):
    """切换 feature.mcp_server (立即生效 + 持久化)。"""
    return await asyncio.to_thread(_toggle, req.enabled)


__all__ = ["router"]

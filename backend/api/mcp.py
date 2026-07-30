"""v1.7 Phase 7 — MCP Server 调试端点 + Settings 端点.

- GET  /api/mcp/status               MCP server 状态 (enabled/transport/tools_count)
- GET  /api/mcp/tools                列出 13 个 tool 元数据
- GET  /api/settings/mcp/config      返回 MCP 端点 + 复制配置 JSON
- PUT  /api/settings/mcp/enabled     切换 feature.mcp_server 开关
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.mcp_config import (
    is_mcp_enabled,
    list_mcp_tools_from_db,
)
from backend.services.feature_flag_service import enable, disable, is_enabled
from backend.logging_config import logger
from backend.version import APP_VERSION as API_VERSION

log = logging.getLogger("hotspot.api.mcp")

router = APIRouter(prefix="/api", tags=["mcp"])


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------
class ToggleEnabledRequest(BaseModel):
    """切换 feature.mcp_server。"""

    enabled: bool


# ---------------------------------------------------------------------------
# /api/mcp/status
# ---------------------------------------------------------------------------
@router.get("/mcp/status")
async def mcp_status():
    """MCP server 状态 (enabled / transport / tools_count)。"""
    enabled = is_mcp_enabled()
    tools = list_mcp_tools_from_db(enabled_only=False) if enabled else []
    return {
        "version": API_VERSION,
        "enabled": enabled,
        "transport": "stdio+sse",
        "sse_endpoint": "/mcp/sse" if enabled else None,
        "stdio_command": "python -m backend.mcp_stdio_main",
        "tools_count": len(tools),
        "spec_version": "2025-06-18",
    }


# ---------------------------------------------------------------------------
# /api/mcp/tools
# ---------------------------------------------------------------------------
@router.get("/mcp/tools")
async def mcp_tools():
    """列出 13 个 tool 的元数据 (name / description / input_schema / enabled)。"""
    if not is_mcp_enabled():
        raise HTTPException(
            status_code=404,
            detail={"message": "MCP server is disabled (feature.mcp_server=False)"},
        )
    tools = list_mcp_tools_from_db(enabled_only=False)
    return {
        "version": API_VERSION,
        "count": len(tools),
        "tools": tools,
    }


# ---------------------------------------------------------------------------
# /api/settings/mcp/config — 返回给前端 MCPSettingsCard 用
# ---------------------------------------------------------------------------
def _build_stdio_config() -> dict:
    """构造 stdio transport 配置 (Claude Desktop / Trae / Cursor / Workbuddy 用)。"""
    cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return {
        "mcpServers": {
            "hotspot": {
                "command": "python",
                "args": ["-m", "backend.mcp_stdio_main"],
                "cwd": cwd,
            }
        }
    }


def _build_sse_config(host: str = "127.0.0.1", port: int = 8000) -> dict:
    """构造 SSE transport 配置 (HTTP 调试用)。"""
    return {
        "mcpServers": {
            "hotspot": {
                "url": f"http://{host}:{port}/mcp/sse",
            }
        }
    }


@router.get("/settings/mcp/config")
async def get_mcp_config():
    """返回 MCP 端点 + 4 个 AI Agent 的 settings.json 示例 (复制用)。"""
    if not is_mcp_enabled():
        raise HTTPException(
            status_code=404,
            detail={"message": "MCP server is disabled"},
        )
    tools = list_mcp_tools_from_db(enabled_only=False)
    read_tools = [t["name"] for t in tools if t["category"] == "read"]
    write_tools = [t["name"] for t in tools if t["category"] == "write"]

    return {
        "version": API_VERSION,
        "enabled": is_mcp_enabled(),
        "stdio": _build_stdio_config(),
        "sse": _build_sse_config(),
        "tools": {
            "read": read_tools,
            "write": write_tools,
        },
        "spec_version": "2025-06-18",
    }


# ---------------------------------------------------------------------------
# /api/settings/mcp/enabled — 切换 feature.mcp_server
# ---------------------------------------------------------------------------
@router.put("/settings/mcp/enabled")
async def toggle_mcp_enabled(req: ToggleEnabledRequest):
    """切换 feature.mcp_server 开关 (重启后生效)。"""
    if req.enabled:
        ok = enable("mcp_server")
    else:
        ok = disable("mcp_server")
    return {
        "version": API_VERSION,
        "enabled": req.enabled,
        "applied": ok,
        "note": "重启 hotspot 后生效",
    }


__all__ = ["router"]

"""v1.7 Phase 7 — MCP Server 配置与工具注册.

设计 (Option A 简化版)
======================
- hotspot 不内置 agent runtime, 不维护 session/heartbeat
- fastapi-mcp 把 9 个 FastAPI 路由自动暴露为 MCP tool
- 双 transport:
  - stdio (默认, 本地单进程, AI Agent 启动)
  - SSE / StreamableHTTP (HTTP, 跨网络/调试用)
- 启动时 idempotent seeding MCP_TOOLS 全部 tool 元数据到 mcp_tool_registry 表 (当前 23)
- feature.mcp_server (默认 True) 控制是否挂载 MCP

关键决策
---------
1. **范围**: 全量 MCP_TOOLS (当前 23, 16 读 + 7 写), 1:1 对应 FastAPI 路由
2. **绑定地址**: 默认 127.0.0.1:8000 (避免远程攻击), 改 0.0.0.0 需 warning log
3. **tool 元数据**: 启动 seeding 到 mcp_tool_registry, 不跨端同步
4. **降级**: 关闭 feature.mcp_server 时 SSE 端点 404, stdio 入口 print 警告并退出
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.api.mcp_operations import MCP_TOOL_OPERATION_IDS
from backend.logging_config import logger

# ----------------------------------------------------------------------------
# SSE 挂载状态 (进程内)
# ----------------------------------------------------------------------------
# 记录 mount_sse_endpoint 是否在本进程成功挂载过 /mcp/sse。
# /api/mcp/status 据此返回真实挂载状态, 避免"端点不存在却声称存在"的误导。
_sse_mounted = False


def is_sse_mounted() -> bool:
    """返回本进程内 /mcp/sse SSE 端点是否已成功挂载。"""
    return _sse_mounted


# ----------------------------------------------------------------------------
# 23 个 MCP tool 对应的 FastAPI operation_id
# ----------------------------------------------------------------------------
# v0.8.7 P3-B 拆出至 mcp_operations.py (本文件行数豁免只许收缩);
# 头部 re-export 保持既有 import 面
# (from backend.api.mcp_config import MCP_TOOL_OPERATION_IDS) 不变。
# 防漂移守卫: test_mcp_server.test_operation_ids_resolve_in_openapi。


def is_mcp_enabled() -> bool:
    """MCP server 本体开关 — 读 ``config.feature_mcp`` (env/.env 可覆盖, 默认 true)。

    双开关契约 (v0.8.2 X-B3 治理, 两键语义不同源、勿合并):
    - 本函数 = server 本体: /mcp/sse 挂载 + tool registry seed + stdio main
    - ``feature_gates.toml`` 的 ``extensions.mcp`` 只控制 /api/mcp/* 调试路由注册
    启动日志 (main.py lifespan) 会以 loguru 同时打印两态, 便于诊断"开了没生效"。
    """
    try:
        from backend.config import config
        return bool(getattr(config, "feature_mcp", True))
    except Exception:
        return False


def build_mcp_server(app):
    """构建 FastApiMCP 实例 (按 MCP_TOOLS 列表 include_operations)。

    Returns: FastApiMCP instance, 或 None (feature 关闭时)
    """
    if not is_mcp_enabled():
        logger.warning("MCP server disabled (feature.mcp_server=False), skipping")
        return None

    from fastapi_mcp import FastApiMCP

    mcp = FastApiMCP(
        app,
        name="hotspot",
        description=(
            "Hotspot Knowledge MCP Server — 让 AI Agent 通过标准 MCP 协议"
            " 读写本地知识库 (MCP_TOOLS, 当前 23 个)"
        ),
        include_operations=MCP_TOOL_OPERATION_IDS,
    )
    return mcp


def mount_sse_endpoint(app, mcp) -> None:
    """挂载 SSE 端点到 FastAPI app, 路径 /mcp/sse。

    仅在 feature.mcp_server=True 且 mcp 实例存在时执行。
    成功挂载后置位 :data:`_sse_mounted`, 供 /api/mcp/status 反映真实状态。
    """
    global _sse_mounted
    if mcp is None:
        return
    try:
        # fastapi-mcp >= 0.4: mount_sse(router, mount_path) 直接注册到 app
        if hasattr(mcp, "mount_sse"):
            mcp.mount_sse(app, mount_path="/mcp/sse")
        else:  # 旧版 fastapi-mcp API 兜底
            mcp.mount_sse_endpoint(path="/mcp/sse")
        _sse_mounted = True
        # DEV-0306 R10: MCP SSE 接入停机哨兵 — 否则有客户端在连时每次停机
        # 白吃满 15s 排空预算 (connect_sse 的读循环不吃哨兵)。
        try:
            from backend.utils.mcp_sse_shutdown import arm_mcp_sse_sentinel
            arm_mcp_sse_sentinel()
        except Exception as e:
            logger.warning(f"arm_mcp_sse_sentinel failed (ignored): {e}")
        logger.info("MCP SSE endpoint mounted at /mcp/sse")
    except Exception as e:
        _sse_mounted = False
        logger.error(f"failed to mount MCP SSE endpoint: {e}")


# ----------------------------------------------------------------------------
# mcp_tool_registry 启动 seeding (idempotent)
# ----------------------------------------------------------------------------
def mcp_tool_registry_seed() -> int:
    """启动时把 MCP_TOOLS 全部 tool 元数据写入 mcp_tool_registry 表。

    幂等: 重启不会重复插入 (用 PRIMARY KEY name 保证)。
    Returns: 实际写入的条数 (首次启动 = 9, 后续 = 0)。
    SQL 在 mcp_tool_registry_repo (Batch 2 D 下沉); 此处只做
    MCP_TOOLS 元数据 → 行的序列化。
    """
    from backend.api.mcp_types import MCP_TOOLS
    from backend.repository.mcp_tool_registry_repo import mcp_tool_registry_repo

    now = datetime.now(timezone.utc).isoformat()

    rows: list[tuple[str, str, str, str, str, str]] = []
    for tool in MCP_TOOLS:
        # 序列化 Pydantic schema 为 JSON Schema
        try:
            input_schema_json = json.dumps(
                tool["input_model"].model_json_schema(),
                ensure_ascii=False,
            )
        except Exception:
            input_schema_json = "{}"
        rows.append((
            tool["name"],
            tool["category"],
            tool["description"],
            input_schema_json,
            "2025-06-18",
            now,
        ))

    inserted = mcp_tool_registry_repo.seed(rows)
    logger.info(
        f"mcp_tool_registry_seed: {inserted}/{len(MCP_TOOLS)} tools inserted"
    )
    return inserted


def list_mcp_tools_from_db(enabled_only: bool = False) -> list[dict]:
    """从 mcp_tool_registry 表读 tool 元数据 (SQL 在 mcp_tool_registry_repo)。"""
    from backend.repository.mcp_tool_registry_repo import (
        _row_to_tool,
        mcp_tool_registry_repo,
    )

    return [_row_to_tool(r) for r in mcp_tool_registry_repo.list_tools(enabled_only)]


__all__ = [
    "MCP_TOOL_OPERATION_IDS",
    "build_mcp_server",
    "is_mcp_enabled",
    "is_sse_mounted",
    "list_mcp_tools_from_db",
    "mcp_tool_registry_seed",
    "mount_sse_endpoint",
]

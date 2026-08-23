"""v1.7 Phase 7 — MCP Server 配置与工具注册.

设计 (Option A 简化版)
======================
- hotspot 不内置 agent runtime, 不维护 session/heartbeat
- fastapi-mcp 把 9 个 FastAPI 路由自动暴露为 MCP tool
- 双 transport:
  - stdio (默认, 本地单进程, AI Agent 启动)
  - SSE / StreamableHTTP (HTTP, 跨网络/调试用)
- 启动时 idempotent seeding 9 个 tool 元数据到 mcp_tool_registry 表
- feature.mcp_server (默认 True) 控制是否挂载 MCP

关键决策
---------
1. **范围**: 全量 9 个 tool (5 读 + 4 写), 1:1 对应 FastAPI 路由
2. **绑定地址**: 默认 127.0.0.1:8000 (避免远程攻击), 改 0.0.0.0 需 warning log
3. **tool 元数据**: 启动 seeding 到 mcp_tool_registry, 不跨端同步
4. **降级**: 关闭 feature.mcp_server 时 SSE 端点 404, stdio 入口 print 警告并退出
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

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
# 9 个 MCP tool 对应的 FastAPI operation_id
# ----------------------------------------------------------------------------
# 与 spec §4 + 当前 main.py 实际路由一致 (OpenAPI schema 已生成)
MCP_TOOL_OPERATION_IDS = [
    # 读 (5)
    "list_hotspots_api_hotspots_get",                              # search_hotspots
    "get_hotspot_api_hotspots__item_id__get",                      # get_hotspot
    "list_favorites_api_favorites_get",                            # list_favorites
    "list_items_api_knowledge_items_get",                          # search_knowledge
    "get_personal_profile_api_profile_get",                        # get_personal_profile (mcp_adapters.py)
    # 写 (4)
    "add_favorite_by_hotspot_api_favorites_by_hotspot_post",       # add_favorite (MCP 入口, 内部查 hotspot + 写 created_via='mcp')
    "remove_favorite_api_favorites__hotspot_id__delete",           # remove_favorite
    "create_annotation_endpoint_api_annotations_post",             # add_annotation
    "update_item_api_knowledge_items__item_id__patch",            # update_knowledge_item
    # v0.5 §18.4: wiki_* 工具族 (llm-wiki-2.0 消费面)
    "wiki_search_api_wiki_search_post",                            # wiki_search
    "wiki_read_api_wiki_read_get",                                 # wiki_read
    "wiki_graph_api_wiki_graph_get",                               # wiki_graph
    "db_trace_api_wiki_trace_post",                                # db_trace
    # v0.5 §18.2 强约束 1: agent 持久产物唯一写路径
    "wiki_write_api_wiki_write_post",                              # wiki_write
]


def is_mcp_enabled() -> bool:
    """读 settings, 检查 feature.mcp_server 状态。"""
    try:
        from backend.config import config
        return bool(getattr(config, "feature_mcp", True))
    except Exception:
        return False


def build_mcp_server(app):
    """构建 FastApiMCP 实例 (按 9 tool 列表 include_operations)。

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
            " 读写本地知识库 (9 个 tool: 5 读 + 4 写)"
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
        logger.info("MCP SSE endpoint mounted at /mcp/sse")
    except Exception as e:
        _sse_mounted = False
        logger.error(f"failed to mount MCP SSE endpoint: {e}")


# ----------------------------------------------------------------------------
# mcp_tool_registry 启动 seeding (idempotent)
# ----------------------------------------------------------------------------
def mcp_tool_registry_seed() -> int:
    """启动时把 9 个 tool 元数据写入 mcp_tool_registry 表。

    幂等: 重启不会重复插入 (用 PRIMARY KEY name 保证)。
    Returns: 实际写入的条数 (首次启动 = 9, 后续 = 0)。
    """
    from backend.api.mcp_types import MCP_TOOLS
    from backend.repository.db import get_connection

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0

    for tool in MCP_TOOLS:
        name = tool["name"]
        input_model = tool["input_model"]
        # 序列化 Pydantic schema 为 JSON Schema
        try:
            input_schema_json = json.dumps(
                input_model.model_json_schema(),
                ensure_ascii=False,
            )
        except Exception:
            input_schema_json = "{}"

        # INSERT OR IGNORE 幂等
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO mcp_tool_registry
                (name, category, description, input_schema, enabled, version, created_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                name,
                tool["category"],
                tool["description"],
                input_schema_json,
                "2025-06-18",
                now,
            ),
        )
        if cur.rowcount > 0:
            inserted += 1

    conn.commit()
    logger.info(
        f"mcp_tool_registry_seed: {inserted}/{len(MCP_TOOLS)} tools inserted"
    )
    return inserted


def list_mcp_tools_from_db(enabled_only: bool = False) -> list[dict]:
    """从 mcp_tool_registry 表读 9 tool 元数据。"""
    from backend.repository.db import get_connection

    conn = get_connection()
    sql = "SELECT name, category, description, input_schema, enabled, version, created_at FROM mcp_tool_registry"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY category, name"
    rows = conn.execute(sql).fetchall()

    tools = []
    for r in rows:
        try:
            schema = json.loads(r["input_schema"]) if r["input_schema"] else {}
        except Exception:
            schema = {}
        tools.append({
            "name": r["name"],
            "category": r["category"],
            "description": r["description"],
            "input_schema": schema,
            "enabled": bool(r["enabled"]),
            "version": r["version"],
            "created_at": r["created_at"],
        })
    return tools


__all__ = [
    "MCP_TOOL_OPERATION_IDS",
    "build_mcp_server",
    "is_mcp_enabled",
    "is_sse_mounted",
    "list_mcp_tools_from_db",
    "mcp_tool_registry_seed",
    "mount_sse_endpoint",
]

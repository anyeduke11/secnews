"""v1.7 Phase 7 — MCP Server Tool 注册表 (模型定义拆出至 mcp_tool_inputs*)。

设计
----
- 23 个 MCP tool (16 读 + 7 写) 的注册表集中定义
- input schema 模型在 ``mcp_tool_inputs.py`` (Phase 7~v0.6 工具族) 与
  ``mcp_tool_inputs_v1.py`` (v0.8.7 P3-B v1 执行域只读导出) — api 层行数纪律
- 用于 fastapi-mcp 自动注册到 MCP server
- 也用于 /api/mcp/tools 调试端点输出
- 不依赖 LLM, hotspot 端只做数据存储 + 工具暴露

调用方
------
- 外部 AI Agent (Cursor / Claude Desktop / Trae / Workbuddy / Claude Code)
- 通过 stdio (默认) 或 SSE (http://127.0.0.1:8000/mcp/sse) 接入
"""
from __future__ import annotations

from backend.api.mcp_tool_inputs import (
    AddAnnotationInput,
    AddFavoriteInput,
    DbTraceInputModel,
    DshAnalyzeInputModel,
    GetHotspotInput,
    GetPersonalProfileInput,
    KlEnqueueInputModel,
    KlRetryInputModel,
    ListFavoritesInput,
    RemoveFavoriteInput,
    SearchHotspotsInput,
    SearchKnowledgeInput,
    UpdateKnowledgeItemInput,
    WikiGraphInput,
    WikiReadInput,
    WikiSearchInputModel,
    WikiWriteInputModel,
)
from backend.api.mcp_tool_inputs_v1 import (
    ListArtifactsInput,
    ListCasesInput,
    ListProposalsInput,
    ListRunsInput,
)

# ===========================================================================
# 23 个 tool 集中注册表 (16 读 + 7 写)
# ===========================================================================
MCP_TOOLS = [
    # 读 (5)
    {
        "name": "search_hotspots",
        "category": "read",
        "description": "搜索 hotspot (多维筛选: 关键词 + 标签 + 时间范围)",
        "input_model": SearchHotspotsInput,
        "fastapi_path": "/api/hotspots",
        "method": "GET",
    },
    {
        "name": "get_hotspot",
        "category": "read",
        "description": "获取单条 hotspot 详情",
        "input_model": GetHotspotInput,
        "fastapi_path": "/api/hotspots/{hotspot_id}",
        "method": "GET",
    },
    {
        "name": "list_favorites",
        "category": "read",
        "description": "列出收藏 (按时间倒序)",
        "input_model": ListFavoritesInput,
        "fastapi_path": "/api/favorites",
        "method": "GET",
    },
    {
        "name": "search_knowledge",
        "category": "read",
        "description": "搜索 knowledge_items 表 (按关键词 + lifecycle)",
        "input_model": SearchKnowledgeInput,
        "fastapi_path": "/api/knowledge/items",
        "method": "GET",
    },
    {
        "name": "get_personal_profile",
        "category": "read",
        "description": "获取个人画像 (EMA 权重 + 兴趣分布)",
        "input_model": GetPersonalProfileInput,
        "fastapi_path": "/api/profile",
        "method": "GET",
    },
    # 写 (4)
    {
        "name": "add_favorite",
        "category": "write",
        "description": "添加收藏 (created_via 自动设为 'mcp')",
        "input_model": AddFavoriteInput,
        "fastapi_path": "/api/favorites",
        "method": "POST",
    },
    {
        "name": "remove_favorite",
        "category": "write",
        "description": "取消收藏",
        "input_model": RemoveFavoriteInput,
        "fastapi_path": "/api/favorites/{hotspot_id}",
        "method": "DELETE",
    },
    {
        "name": "add_annotation",
        "category": "write",
        "description": "为 hotspot 或 knowledge_item 添加笔记/标注",
        "input_model": AddAnnotationInput,
        "fastapi_path": "/api/annotations",
        "method": "POST",
    },
    {
        "name": "update_knowledge_item",
        "category": "write",
        "description": "更新 knowledge_item 字段 (lifecycle/tags/concepts/...)",
        "input_model": UpdateKnowledgeItemInput,
        "fastapi_path": "/api/knowledge/items/{item_id}",
        "method": "PATCH",
    },
    # v0.5 §18.4: wiki_* (4)
    {
        "name": "wiki_search",
        "category": "read",
        "description": "全文搜索 llm-wiki-2.0 知识条目 chunks (中英文)",
        "input_model": WikiSearchInputModel,
        "fastapi_path": "/api/wiki/search",
        "method": "POST",
    },
    {
        "name": "wiki_read",
        "category": "read",
        "description": "读取 llm-wiki-2.0 单个 .md 文件全文",
        "input_model": WikiReadInput,
        "fastapi_path": "/api/wiki/read",
        "method": "GET",
    },
    {
        "name": "wiki_graph",
        "category": "read",
        "description": "概念邻接查询 (concepts/graph.json BFS)",
        "input_model": WikiGraphInput,
        "fastapi_path": "/api/wiki/graph",
        "method": "GET",
    },
    {
        "name": "db_trace",
        "category": "read",
        "description": "反查知识条目的事件来源 (wiki_events 桥接表)",
        "input_model": DbTraceInputModel,
        "fastapi_path": "/api/wiki/trace",
        "method": "POST",
    },
    # v0.5 §18.2 强约束 1: agent 持久产物唯一写路径
    {
        "name": "wiki_write",
        "category": "write",
        "description": "agent 持久产物写回 llm-wiki-2.0 (经 ai_hub 单写路径)",
        "input_model": WikiWriteInputModel,
        "fastapi_path": "/api/wiki/write",
        "method": "POST",
    },
    # v0.6 Phase 5 commit 3: 5 个 MCP tool 扩展 (KL 推进 + DSH 分析)
    {
        "name": "kl_enqueue",
        "category": "write",
        "description": "推进单个 knowledge item 到下一阶段 (kl_state_machine 校验)",
        "input_model": KlEnqueueInputModel,
        "fastapi_path": "/api/mcp/kl/enqueue",
        "method": "POST",
    },
    {
        "name": "kl_status",
        "category": "read",
        "description": "返回 KL pipeline 漏斗 + 队列 + 错误 + 计数",
        "input_model": None,  # 无入参
        "fastapi_path": "/api/mcp/kl/status",
        "method": "GET",
    },
    {
        "name": "kl_retry",
        "category": "write",
        "description": "重试 KL pipeline 错误任务 (可选按 wiki_id 过滤)",
        "input_model": KlRetryInputModel,
        "fastapi_path": "/api/mcp/kl/retry",
        "method": "POST",
    },
    {
        "name": "dsh_analyze",
        "category": "read",
        "description": "调用 DSH classify 任务 (DSH 不可达时 fallback LLM)",
        "input_model": DshAnalyzeInputModel,
        "fastapi_path": "/api/mcp/dsh/analyze",
        "method": "POST",
    },
    {
        "name": "dsh_session",
        "category": "read",
        "description": "查询 DSH 会话状态 (按 session_id)",
        "input_model": None,  # session_id 在 path 中
        "fastapi_path": "/api/mcp/dsh/session/{session_id}",
        "method": "GET",
    },
    # v0.8.7 P3-B: v1 执行域只读导出 (4) — 外部 agent 只读观测, 不产提案
    {
        "name": "list_proposals",
        "category": "read",
        "description": "列出提案账本 (人主律: 提案 ≠ 事实, 只读)",
        "input_model": ListProposalsInput,
        "fastapi_path": "/api/proposals",
        "method": "GET",
    },
    {
        "name": "list_runs",
        "category": "read",
        "description": "按 action 列出执行 run (run 账本)",
        "input_model": ListRunsInput,
        "fastapi_path": "/api/v1/runs",
        "method": "GET",
    },
    {
        "name": "list_artifacts",
        "category": "read",
        "description": "按 run 列出产物 (done 必有产物的对账面)",
        "input_model": ListArtifactsInput,
        "fastapi_path": "/api/v1/artifacts",
        "method": "GET",
    },
    {
        "name": "list_cases",
        "category": "read",
        "description": "列出案件队列 (status/priority/owner_role/subject_id 过滤)",
        "input_model": ListCasesInput,
        "fastapi_path": "/api/v1/cases",
        "method": "GET",
    },
]


__all__ = [
    "MCP_TOOLS",
    "AddAnnotationInput",
    "AddFavoriteInput",
    "DbTraceInputModel",
    "DshAnalyzeInputModel",
    "GetHotspotInput",
    "GetPersonalProfileInput",
    "KlEnqueueInputModel",
    "KlRetryInputModel",
    "ListArtifactsInput",
    "ListCasesInput",
    "ListFavoritesInput",
    "ListProposalsInput",
    "ListRunsInput",
    "RemoveFavoriteInput",
    "SearchHotspotsInput",
    "SearchKnowledgeInput",
    "UpdateKnowledgeItemInput",
    "WikiGraphInput",
    "WikiReadInput",
    "WikiSearchInputModel",
    "WikiWriteInputModel",
]

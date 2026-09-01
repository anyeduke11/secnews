"""v1.7 Phase 7 — MCP Server Tool 输入/输出 Pydantic 模型.

设计
----
- 9 个 MCP tool (5 读 + 4 写) 的 input schema 集中定义
- 用于 fastapi-mcp 自动注册到 MCP server
- 也用于 /api/mcp/tools 调试端点输出
- 不依赖 LLM, hotspot 端只做数据存储 + 工具暴露

调用方
------
- 外部 AI Agent (Cursor / Claude Desktop / Trae / Workbuddy / Claude Code)
- 通过 stdio (默认) 或 SSE (http://127.0.0.1:8000/mcp/sse) 接入
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ===========================================================================
# 5 个读 tool
# ===========================================================================
class SearchHotspotsInput(BaseModel):
    """search_hotspots — 搜索热点。"""

    q: str = Field("", description="关键词 (空=全部)")
    tags: list[str] | None = Field(None, description="标签过滤")
    tag_mode: str = Field("or", description="and | or")
    time_range: str = Field("D7", description="H24 | D3 | D7 | D30 | W1 | ALL")
    limit: int = Field(20, ge=1, le=100, description="返回条数上限")


class GetHotspotInput(BaseModel):
    """get_hotspot — 获取单条热点详情。"""

    hotspot_id: str = Field(..., min_length=1, description="hotspot ID")


class ListFavoritesInput(BaseModel):
    """list_favorites — 列出收藏。"""

    limit: int = Field(50, ge=1, le=500)
    cursor: str | None = Field(None, description="分页游标 (favorited_at)")


class SearchKnowledgeInput(BaseModel):
    """search_knowledge — 搜索知识库。"""

    q: str = Field(..., min_length=1, description="查询关键词")
    lifecycle: str | None = Field(None, description="signal | generate | refine | compose")
    limit: int = Field(20, ge=1, le=100)


class GetPersonalProfileInput(BaseModel):
    """get_personal_profile — 获取个人画像 (无入参)。"""

    pass


# ===========================================================================
# 4 个写 tool
# ===========================================================================
class AddFavoriteInput(BaseModel):
    """add_favorite — 添加收藏 (created_via 自动设为 'mcp')。"""

    hotspot_id: str = Field(..., min_length=1)
    note: str = Field("", description="可选备注 (将来用于 annotation)")


class RemoveFavoriteInput(BaseModel):
    """remove_favorite — 取消收藏。"""

    hotspot_id: str = Field(..., min_length=1)


class AddAnnotationInput(BaseModel):
    """add_annotation — 添加笔记/标注。"""

    entity_type: str = Field(..., description="hotspot | knowledge_item")
    entity_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class UpdateKnowledgeItemInput(BaseModel):
    """update_knowledge_item — 更新知识条目字段。"""

    item_id: str = Field(..., min_length=1)
    fields: dict = Field(..., description="待更新字段 (title/lifecycle/tags/concepts/...)")


# ===========================================================================
# v0.5 §18.4: wiki_* 工具族 (4 个读为主)
# ===========================================================================
class WikiSearchInputModel(BaseModel):
    """wiki_search — 全文搜索 llm-wiki-2.0。"""

    q: str = Field(..., min_length=1, description="查询关键词")
    limit: int = Field(20, ge=1, le=50)


class WikiReadInput(BaseModel):
    """wiki_read — 读单个 .md 全文。"""

    path: str = Field(..., min_length=1, description="相对 knowledge/ 的路径")


class WikiGraphInput(BaseModel):
    """wiki_graph — 概念邻接。"""

    concept: str = Field(..., min_length=1)
    depth: int = Field(1, ge=1, le=2)


class DbTraceInputModel(BaseModel):
    """db_trace — 反查事件对应。"""

    wiki_path: str = Field("")
    db_table: str = Field("")
    db_row_id: str = Field("")
    limit: int = Field(50, ge=1, le=200)


class WikiWriteInputModel(BaseModel):
    """wiki_write — agent 持久产物写回 llm-wiki-2.0 (经 ai_hub 单写路径)。"""

    item_id: str = Field(..., min_length=1, max_length=120,
                         description="条目 ID (即文件名 stem)")
    title: str = Field(..., min_length=1, description="标题")
    content: str = Field("", description="Markdown 正文 (不含 frontmatter)")
    source: str = Field("mcp", description="来源标识")
    source_url: str = Field("", description="原文 URL (可选)")
    tags: list[str] = Field(default_factory=list, description="标签")


# ===========================================================================
# v0.6 Phase 5 commit 3: KL/DSH 工具族 (5 个 — KL 推进/状态/重试 + DSH 分析/会话)
# ===========================================================================
class KlEnqueueInputModel(BaseModel):
    """kl_enqueue — 推进单个 knowledge item 到下一阶段 (kl_state_machine 校验)."""

    item_id: str = Field(..., min_length=1, description="knowledge item id (wiki file stem)")


class KlRetryInputModel(BaseModel):
    """kl_retry — 重试错误任务 (可选按 wiki_id 过滤)."""

    wiki_id: str | None = Field(None, description="可选, 仅重试指定 wiki_id 的错误任务")


class DshAnalyzeInputModel(BaseModel):
    """dsh_analyze — 调用 DSH classify 任务 (fallback LLM)."""

    content: str = Field(..., min_length=1, description="待分类文本 (URL/标题/段落)")
    hint: str | None = Field(None, description="可选上下文 (用于引导分类标签)")



# ===========================================================================
# 19 个 tool 集中注册表 (12 读 + 7 写)
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
    "ListFavoritesInput",
    "RemoveFavoriteInput",
    "SearchHotspotsInput",
    "SearchKnowledgeInput",
    "UpdateKnowledgeItemInput",
    "WikiGraphInput",
    "WikiReadInput",
    "WikiSearchInputModel",
    "WikiWriteInputModel",
]

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
# 9 个 tool 集中注册表
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
]


__all__ = [
    "MCP_TOOLS",
    "AddAnnotationInput",
    "AddFavoriteInput",
    "GetHotspotInput",
    "GetPersonalProfileInput",
    "ListFavoritesInput",
    "RemoveFavoriteInput",
    "SearchHotspotsInput",
    "SearchKnowledgeInput",
    "UpdateKnowledgeItemInput",
]

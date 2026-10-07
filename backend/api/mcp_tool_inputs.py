"""MCP tool 输入 Pydantic 模型 (v0.8.7 P3-B 自 mcp_types 拆出, api 层行数纪律)。

schema 用途: fastapi-mcp 注册 + /api/mcp/tools 调试端点 + mcp_tool_registry
seeding (见 mcp_types.MCP_TOOLS 注册表)。模型命名与字段镜像对应 FastAPI
端点的查询参数 (ge/le 对齐)。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# 5 个读 tool (Phase 7 基础)
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


# 4 个写 tool (Phase 7 基础)
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


# wiki_* 工具族 (v0.5 §18.4) + wiki_write (v0.5 §18.2 唯一写路径)
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
    """wiki_write — agent 持久产物写回 llm-wiki-2.0 (经 ai_write_back 单写路径)。"""

    item_id: str = Field(..., min_length=1, max_length=120,
                         description="条目 ID (即文件名 stem)")
    title: str = Field(..., min_length=1, description="标题")
    content: str = Field("", description="Markdown 正文 (不含 frontmatter)")
    source: str = Field("mcp", description="来源标识")
    source_url: str = Field("", description="原文 URL (可选)")
    tags: list[str] = Field(default_factory=list, description="标签")


# KL/DSH 工具族 (v0.6 Phase 5 commit 3)
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

"""v1.7 Phase 3 — 统一跨层搜索服务.

跨 hotspots + knowledge_items 的统一搜索，基于 migration 033 创建的
``unified_search`` 视图 (UNION ALL of hotspots + knowledge_items).

设计决策
---------
- 使用 ``unified_search`` 视图 + LIKE 匹配，而非 ``unified_fts`` FTS5 MATCH。
  原因: ``unified_fts`` 是 FTS5 虚拟表但 migration 033 未创建同步触发器，
  手动维护双源 (hotspots + knowledge_items) 的 FTS5 触发器复杂度高 (delete
  需 rowid 映射)。LIKE 在 10k 行级别 (<10ms) 足以满足验收 2 的 P95 < 500ms
  预算。FTS5 优化推迟到性能瓶颈出现时。
- ``sources`` 参数映射到 ``entity_type`` 列 ('hotspot' / 'knowledge')。
- 大小写不敏感: 用 ``LOWER(title) LIKE LOWER(?)`` 兼容 SQLite 默认大小写
  不敏感的 LIKE，但显式 LOWER 保证可移植性。
"""
from __future__ import annotations

import re
from typing import Optional

from backend.repository.db import get_connection

# 限制单次返回上限，防止全表扫描型查询拖垮响应时间。
_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20

# 允许的 source 过滤值 (对应 unified_search.entity_type)
_VALID_SOURCES = {"hotspot", "knowledge"}


def _sanitize_query(q: str) -> str:
    """转义 LIKE 通配符，避免用户输入 ``%`` / ``_`` 导致意外匹配。

    保留搜索词的字面语义: 用户输入 ``100%`` 应匹配 ``100%`` 而非 ``100X``。
    """
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def unified_search(
    q: str,
    sources: Optional[list[str]] = None,
    limit: int = _DEFAULT_LIMIT,
) -> dict:
    """跨层统一搜索。

    Parameters
    ----------
    q:
        搜索关键词。空字符串返回空结果 (不报错)。
    sources:
        可选实体类型过滤。``["hotspot"]`` 仅搜热点，``["knowledge"]`` 仅搜
        知识库。``None`` 或空列表表示全部。非法值被忽略。
    limit:
        最大返回条数，上限 100。

    Returns
    -------
    dict
        ``{"query": q, "items": [...], "grouped": {"hotspot": [...], ...}}``
        - ``items``: 按时间倒序的扁平结果列表
        - ``grouped``: 按 entity_type 分组的结果 (便于前端分栏渲染)
    """
    query = (q or "").strip()
    effective_limit = max(1, min(limit, _MAX_LIMIT))

    if not query:
        return {"query": q or "", "items": [], "grouped": {}}

    # 过滤非法 source 值，只保留有效的 entity_type
    effective_sources: list[str] = []
    if sources:
        for s in sources:
            s_norm = s.strip().lower()
            if s_norm in _VALID_SOURCES:
                effective_sources.append(s_norm)

    where_clauses: list[str] = [
        "(LOWER(title) LIKE LOWER(?) ESCAPE '\\' "
        "OR LOWER(summary) LIKE LOWER(?) ESCAPE '\\')"
    ]
    escaped = _sanitize_query(query)
    pattern = f"%{escaped}%"
    params: list = [pattern, pattern]

    if effective_sources:
        placeholders = ",".join("?" * len(effective_sources))
        where_clauses.append(f"entity_type IN ({placeholders})")
        params.extend(effective_sources)

    params.append(effective_limit)

    sql = f"""
        SELECT entity_type, entity_id, title, summary, category, ingested_at
        FROM unified_search
        WHERE {' AND '.join(where_clauses)}
        ORDER BY ingested_at DESC
        LIMIT ?
    """

    rows = get_connection().execute(sql, params).fetchall()

    items: list[dict] = []
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        item = {
            "entity_type": r["entity_type"],
            "entity_id": r["entity_id"],
            "title": r["title"],
            "summary": r["summary"],
            "category": r["category"],
            "ingested_at": r["ingested_at"],
        }
        items.append(item)
        grouped.setdefault(item["entity_type"], []).append(item)

    return {"query": q, "items": items, "grouped": grouped}


def search_hotspots_only(q: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
    """便捷方法: 仅搜索 hotspots 层。"""
    result = unified_search(q, sources=["hotspot"], limit=limit)
    return result["items"]


def search_knowledge_only(q: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
    """便捷方法: 仅搜索 knowledge_items 层。"""
    result = unified_search(q, sources=["knowledge"], limit=limit)
    return result["items"]


__all__ = [
    "unified_search",
    "search_hotspots_only",
    "search_knowledge_only",
]

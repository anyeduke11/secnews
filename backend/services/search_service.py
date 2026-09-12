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
- ``sources`` 参数映射到 ``entity_type`` 列 ('hotspot' / 'knowledge' /
  'wiki')。'wiki' 走 FTS5 MATCH (migration 073 维护), 与 LIKE 兜底并存。
- 大小写不敏感: 用 ``LOWER(title) LIKE LOWER(?)`` 兼容 SQLite 默认大小写
  不敏感的 LIKE，但显式 LOWER 保证可移植性。
"""
from __future__ import annotations

from backend.repository.db import get_connection, knowledge_items_table

# 限制单次返回上限，防止全表扫描型查询拖垮响应时间。
_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20

# 允许的 source 过滤值 (对应 unified_search.entity_type + wiki_items_fts 旁路)
_VALID_SOURCES = {"hotspot", "knowledge", "wiki"}


def _sanitize_query(q: str) -> str:
    """转义 LIKE 通配符，避免用户输入 ``%`` / ``_`` 导致意外匹配。

    保留搜索词的字面语义: 用户输入 ``100%`` 应匹配 ``100%`` 而非 ``100X``。
    """
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def unified_search(
    q: str,
    sources: list[str] | None = None,
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

    # v085-review F11: 恢复 pre-R21 契约 (docstring 明示 "None/空列表 = 全部")。
    # R21 重写 (f52bf51) 后空 effective_sources → sql_parts 空 → 恒空结果,
    # 30 个 search/FTS 测试全红 (v1.0.1 融合带入的预存回归)。
    # 缺省 = hotspot + knowledge (与旧 unified_search 视图口径一致, 视图只含
    # 这两层); wiki 仍需显式传入才走 FTS 旁路。
    if not effective_sources:
        effective_sources = ["hotspot", "knowledge"]

    where_clauses: list[str] = [
        ("(LOWER(title) LIKE LOWER(?) ESCAPE '\\' "
        "OR LOWER(summary) LIKE LOWER(?) ESCAPE '\\')")
    ]
    escaped = _sanitize_query(query)
    pattern = f"%{escaped}%"
    params: list = [pattern, pattern]

    # LIKE 兜底路径: hotspot + knowledge (entity_type 不含 'wiki')
    like_sources = [s for s in effective_sources if s != "wiki"]

    # v1.0 R21 服务恢复: unified_search view 已 DROP (migration 106);
    # 改走 service 层 ATTACH 跨 db UNION ALL — hot.hotspots ∪ warm.knowledge_items
    # 跨 db UNION 在 SQLite 受限 (单 query 内的 db name 可引用 ATTACH 后的别名)
    # 拆分两条 SELECT 用 ATTACH 别名 (warm.knowledge_items 在 get_connection 已挂载)
    sql_parts: list[str] = []
    sql_params: list = []

    if "hotspot" in like_sources:
        sql_parts.append("""
            SELECT 'hotspot' AS entity_type, h.id AS entity_id, h.title AS title,
                   h.summary AS summary, h.category AS category, h.ingested_at AS ingested_at
            FROM hotspots h
            WHERE (LOWER(h.title) LIKE LOWER(?) ESCAPE '\\' OR LOWER(h.summary) LIKE LOWER(?) ESCAPE '\\')
        """)
        sql_params.extend([pattern, pattern])

    if "knowledge" in like_sources:
        ktbl = knowledge_items_table()
        sql_parts.append(f"""
            SELECT 'knowledge' AS entity_type, k.id AS entity_id, k.title AS title,
                   k.topic AS summary, k.domain AS category, k.ingested_at AS ingested_at
            FROM {ktbl} k
            WHERE (LOWER(k.title) LIKE LOWER(?) ESCAPE '\\' OR LOWER(k.topic) LIKE LOWER(?) ESCAPE '\\')
        """)
        sql_params.extend([pattern, pattern])

    if sql_parts:
        sql = " UNION ALL ".join(sql_parts) + " ORDER BY ingested_at DESC LIMIT ?"
        sql_params.append(effective_limit)

        rows = get_connection().execute(sql, sql_params).fetchall()
    else:
        # F11: 仅请求 wiki 时 LIKE/UNION 不参与, 直接落到下方 FTS 旁路
        # (R21 版在此早退空结果, wiki-only 搜索恒空)
        rows = []

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

    # 'wiki' source 走 FTS5 MATCH 旁路 (migration 073 维护 wiki_items_fts)
    if "wiki" in effective_sources:
        wiki_hits = _search_wiki_fts(query, effective_limit)
        items.extend(wiki_hits)
        grouped.setdefault("wiki", []).extend(wiki_hits)

    return {"query": q, "items": items, "grouped": grouped}


def _search_wiki_fts(q: str, limit: int) -> list[dict]:
    """FTS5 MATCH 旁路: 走 wiki_items_fts (MATCH 真相关度排序) + LEFT JOIN
    knowledge_items 回查 title / topic / ingested_at.

    注意 wiki_items_fts 是 contentless FTS5 (content=''); FTS5 行只存索引,
    列投影 (f.title / f.id) 总是 NULL — 必须靠 LEFT JOIN knowledge_items
    按 rowid 回查实体字段。所以 entity_id 也用 k.id (而不是 f.id), 避免
    返回 None。snippet() 仍可用 (FTS5 内部存词位 + 偏移)。
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT
                IFNULL(k.id, f.id) AS entity_id,
                IFNULL(k.title, '') AS title,
                IFNULL(k.topic, '') AS summary,
                IFNULL(k.type, '') AS category,
                IFNULL(k.ingested_at, '') AS ingested_at,
                snippet(wiki_items_fts, 1, '[', ']', '...', 12) AS fts_snippet
            FROM wiki_items_fts f
            LEFT JOIN {knowledge_items_table()} k ON k.rowid = f.rowid
            WHERE wiki_items_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (q, limit),
        ).fetchall()
    except Exception:
        # FTS5 syntax errors on malformed query → 空结果而非 5xx
        return []

    items: list[dict] = []
    for r in rows:
        items.append(
            {
                "entity_type": "wiki",
                "entity_id": r["entity_id"],
                "title": r["title"] or "",
                "summary": r["summary"],
                "category": r["category"],
                "ingested_at": r["ingested_at"],
                "fts_snippet": r["fts_snippet"],
            }
        )
    return items


def search_hotspots_only(q: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
    """便捷方法: 仅搜索 hotspots 层。"""
    result = unified_search(q, sources=["hotspot"], limit=limit)
    return result["items"]


def search_knowledge_only(q: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
    """便捷方法: 仅搜索 knowledge_items 层。"""
    result = unified_search(q, sources=["knowledge"], limit=limit)
    return result["items"]


def search_wiki_only(q: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
    """便捷方法: 仅走 wiki_items_fts FTS5 MATCH, 真相关度排序.

    与 search_knowledge_only (LIKE 兜底) 并存; 走纯 FTS5 索引, 不经 unified_search.
    """
    return _search_wiki_fts(q, max(1, min(limit, _MAX_LIMIT)))


__all__ = [
    "search_hotspots_only",
    "search_knowledge_only",
    "search_wiki_only",
    "unified_search",
]

"""v1.7 Phase 3 → P4 重构 — 统一跨层搜索服务 (DEV-0296)。

跨 hotspots + knowledge_items 的统一搜索。

引擎分层 (P4 重构, 依据批判性审查四项结构性问题):
- **hotspots/knowledge: FTS5 主引擎** — hotspots_fts (001_init 触发器同步,
  索引 title+summary) 与 wiki_items_fts (073 同步, 即 knowledge_items 的
  FTS, 索引 title+topic+tags+type) MATCH, 相关度 rank 排序; FTS 故障时
  LIKE 兜底 (Phase 3 路径保留为降级面)。
- **查询预处理 (P4-2)**: 空格分词 → 每词 FTS 短语包裹 (隐式 AND, 救多词
  查询假阴性); 内嵌引号按 FTS5 规则翻倍; `-` 不再外泄 (CVE-2026-1234
  整体短语化, 不再被解析为 NOT); FTS 语法错误静默落 LIKE 兜底而非空结果。

设计决策 (继承 Phase 3 + P4 修订)
----------
- wiki 旁路走 wiki_items_fts MATCH (migration 073 维护)。
- LIKE 兜底: hotspots/knowledge 的 fallback, 非 wiki (无对应 LIKE 面,
  wiki FTS 故障属索引损坏, 不静默换弱引擎)。
- 大小写不敏感: LIKE 路径显式 LOWER。
"""
from __future__ import annotations

from backend.repository.db import get_connection, knowledge_items_table

# 限制单次返回上限，防止全表扫描型查询拖垮响应时间。
_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20

# 允许的 source 过滤值 (对应 entity_type + wiki_items_fts 旁路)
_VALID_SOURCES = {"hotspot", "knowledge", "wiki"}


def _sanitize_like(q: str) -> str:
    """LIKE 通配符转义 (继承 Phase 3): 保留搜索词的字面语义。"""
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_fts_query(q: str) -> str:
    """查询预处理 (P4-2): 空格分词 → 每词 FTS5 短语包裹 (隐式 AND)。

    - ``CVE-2026-1234`` → ``"CVE-2026-1234"`` (整体短语, 不再被 FTS5
      解析为 CVE NOT 2026...; unicode61 分词下短语内的 - 连接词仍可命中)
    - ``勒索软件 金融机构`` → ``"勒索软件" "金融机构"`` (AND, 救多词假阴性)
    - 内嵌双引号翻倍 (FTS5 escaping); 空词被过滤。
    """
    tokens = [t for t in (q or "").split() if t]
    return " ".join(f'"{t.replace(chr(34), chr(34) * 2)}"' for t in tokens)


def unified_search(
    q: str,
    sources: list[str] | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> dict:
    """跨层统一搜索 (FTS5 主引擎 + LIKE 兜底)。

    Parameters
    ----------
    q:
        搜索关键词。空字符串返回空结果 (不报错)。
    sources:
        可选实体类型过滤。``["hotspot"]`` 仅搜热点, ``["knowledge"]`` 仅搜
        知识库。``None`` 或空列表 = hotspot + knowledge (wiki 需显式传入,
        F11 契约继承)。
    limit:
        最大返回条数，上限 100。

    Returns
    -------
    dict
        ``{"query": q, "items": [...], "grouped": {...}}``
        item 新增 ``url`` 字段 (P4-1: 结果可点回原文; wiki 类为 wiki_path)。
    """
    query = (q or "").strip()
    effective_limit = max(1, min(limit, _MAX_LIMIT))

    if not query:
        return {"query": q or "", "items": [], "grouped": {}}

    effective_sources: list[str] = []
    if sources:
        for s in sources:
            s_norm = s.strip().lower()
            if s_norm in _VALID_SOURCES:
                effective_sources.append(s_norm)
    if not effective_sources:
        effective_sources = ["hotspot", "knowledge"]

    fts_query = build_fts_query(query)
    like_sources = [s for s in effective_sources if s != "wiki"]

    items: list[dict] = []
    grouped: dict[str, list[dict]] = {}

    if like_sources:
        fts_tables = []
        if "hotspot" in like_sources:
            fts_tables.append(("hotspot", "hotspots_fts"))
        if "knowledge" in like_sources:
            fts_tables.append(("knowledge", "wiki_items_fts"))

        for entity, table in fts_tables:
            rows = _fts_search_entity(table, fts_query, effective_limit)
            if rows is None:
                # FTS 索引缺失/语法故障 → LIKE 兜底
                rows = _like_search_entity(entity, query, effective_limit)
            elif not rows:
                # FTS 零命中 → LIKE 兜底自愈: 覆盖索引滞后 (contentless 表靠
                # 异步 job 回填, 冷启动/测试直接插行无 FTS) 与 unicode61 分词
                # 对 CJK 无空格切分的盲区 — LIKE 全表扫保真, 宁多查勿假阴性。
                rows = _like_search_entity(entity, query, effective_limit)
            items.extend(rows or [])

    items.sort(key=lambda x: x.get("ingested_at") or "", reverse=True)
    for it in items:
        grouped.setdefault(it["entity_type"], []).append(it)

    if "wiki" in effective_sources:
        wiki_hits = _search_wiki_fts(fts_query, effective_limit)
        items.extend(wiki_hits)
        grouped.setdefault("wiki", []).extend(wiki_hits)

    return {"query": q, "items": items, "grouped": grouped}


def _fts_search_entity(
    table: str, fts_query: str, limit: int,
) -> list[dict] | None:
    """单实体 FTS5 检索 (相关度 rank 排序)。None = FTS 层故障 → 调用方走 LIKE。

    - hotspots_fts: rowid = hotspots.rowid (001 触发器维护)
    - wiki_items_fts: contentless + rowid = knowledge_items.rowid (073 维护)
      列投影需 LEFT JOIN 回查 (contentless FTS 列值全 NULL)
    """
    conn = get_connection()
    ktbl = knowledge_items_table()
    if table == "hotspots_fts":
        sql = """
            SELECT h.id AS entity_id, h.title AS title, h.summary AS summary,
                   h.category AS category, h.ingested_at AS ingested_at,
                   h.url AS url, 'hotspot' AS entity_type
            FROM hotspots_fts f
            JOIN hotspots h ON h.rowid = f.rowid
            WHERE hotspots_fts MATCH ?
              AND h.is_hidden = 0
            ORDER BY rank, h.ingested_at DESC
            LIMIT ?
        """
        params: tuple = (fts_query, limit)
    else:
        sql = f"""
            SELECT k.id AS entity_id,
                   IFNULL(k.title, '') AS title,
                   IFNULL(k.topic, '') AS summary,
                   IFNULL(k.type, '') AS category,
                   IFNULL(k.ingested_at, '') AS ingested_at,
                   '' AS url,
                   'knowledge' AS entity_type
            FROM wiki_items_fts f
            LEFT JOIN {ktbl} k ON k.rowid = f.rowid
            WHERE wiki_items_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        params = (fts_query, limit)
    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception:
        return None  # 索引缺失/语法问题 → 上层 LIKE 兜底
    return [
        {
            "entity_type": r["entity_type"],
            "entity_id": r["entity_id"],
            "title": r["title"],
            "summary": r["summary"],
            "category": r["category"],
            "ingested_at": r["ingested_at"],
            "url": r["url"],
        }
        for r in rows
    ]


def _like_search_entity(
    entity: str, query: str, limit: int,
) -> list[dict]:
    """LIKE 兜底 (Phase 3 路径保留为降级面): FTS 故障/零命中时可依赖。

    多词 LIKE 语义: 分词后逐词 AND (每个词都要命中), 与 FTS 隐式 AND 对齐 —
    单词查询行为与 Phase 3 完全一致。
    """
    conn = get_connection()
    tokens = [t for t in query.split() if t]
    if not tokens:
        return []
    clauses = []
    params: list = []
    for t in tokens:
        clauses.append(
            "(LOWER(title) LIKE LOWER(?) ESCAPE '\\' "
            "OR LOWER(summary) LIKE LOWER(?) ESCAPE '\\')"
        )
        p = f"%{_sanitize_like(t)}%"
        params.extend([p, p])

    if entity == "hotspot":
        sql = f"""
            SELECT h.id AS entity_id, h.title AS title, h.summary AS summary,
                   h.category AS category, h.ingested_at AS ingested_at,
                   h.url AS url, 'hotspot' AS entity_type
            FROM hotspots h
            WHERE h.is_hidden = 0 AND {' AND '.join(clauses)}
            ORDER BY h.ingested_at DESC LIMIT ?
        """
        params.append(limit)
    else:
        ktbl = knowledge_items_table()
        # knowledge 的第二匹配列是 topic (无 summary 列)
        clauses_k = [
            "(LOWER(title) LIKE LOWER(?) ESCAPE '\\' "
            "OR LOWER(topic) LIKE LOWER(?) ESCAPE '\\')"
            for _ in tokens
        ]
        sql = f"""
            SELECT k.id AS entity_id, k.title AS title, k.topic AS summary,
                   k.domain AS category, k.ingested_at AS ingested_at,
                   '' AS url, 'knowledge' AS entity_type
            FROM {ktbl} k
            WHERE {' AND '.join(clauses_k)}
            ORDER BY k.ingested_at DESC LIMIT ?
        """
        params = []
        for t in tokens:
            p = f"%{_sanitize_like(t)}%"
            params.extend([p, p])
        params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "entity_type": r["entity_type"],
            "entity_id": r["entity_id"],
            "title": r["title"],
            "summary": r["summary"],
            "category": r["category"],
            "ingested_at": r["ingested_at"],
            "url": r["url"],
        }
        for r in rows
    ]


def _search_wiki_fts(fts_query: str, limit: int) -> list[dict]:
    """wiki_items_fts MATCH 旁路 (FTS5 短语化查询 + LEFT JOIN 回查实体字段)。

    contentless FTS5 列投影总是 NULL — 靠 LEFT JOIN knowledge_items 按
    rowid 回查; ``url`` 放 wiki_path 供前端构造深读锚点 (P4-1)。
    """
    conn = get_connection()
    ktbl = knowledge_items_table()
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
            LEFT JOIN {ktbl} k ON k.rowid = f.rowid
            WHERE wiki_items_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
    except Exception:
        # FTS 语法/索引故障 → 空结果而非 5xx (wiki 无 LIKE 兜底面)
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
                "url": "",
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
    """便捷方法: 仅走 wiki_items_fts FTS5 MATCH (真相关度排序)。"""
    fts_query = build_fts_query(q)
    if not fts_query:
        return []
    return _search_wiki_fts(fts_query, max(1, min(limit, _MAX_LIMIT)))


__all__ = [
    "build_fts_query",
    "search_hotspots_only",
    "search_knowledge_only",
    "search_wiki_only",
    "unified_search",
]

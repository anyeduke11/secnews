"""v1.7 Phase 4 — 上下文推荐服务.

PRD §3.2.7: 基于标签重叠度的上下文推荐。

核心函数
---------
- ``recommend(entity_type, entity_id, limit)`` — 跨层推荐
  - ``entity_type="knowledge"``: 基于 knowledge_items.tags 列做标签重叠
  - ``entity_type="hotspot"``: 基于 hotspot_tags 关联表做标签重叠

评分算法
---------
标签重叠度 (Jaccard 简化版):
::

    score = |tags(item) ∩ tags(candidate)|

分数越高越相关。同分时按 ingested_at 降序 (更新的优先)。

验收 2: "知识推荐侧栏显示相关条目"
  → 给定一个 knowledge item, recommend() 应返回有共享标签的其他 items
"""
from __future__ import annotations

from typing import Optional

from backend.repository.db import get_connection
from backend.repository.knowledge_repo import knowledge_repo
from backend.repository.tags_repo import TagRepository

_MAX_LIMIT = 20
_DEFAULT_LIMIT = 5


def _get_knowledge_tags(item_id: str) -> set[str]:
    """读取一个 knowledge item 的标签集合。"""
    item = knowledge_repo.get_item(item_id)
    if item is None:
        return set()
    return set(item.tags or [])


def _get_hotspot_tags(hotspot_id: str) -> set[str]:
    """读取一个 hotspot 的标签集合 (从 hotspot_tags 关联表)。"""
    tags = TagRepository().list_by_hotspot(hotspot_id)
    return {t.id for t in tags}


def recommend_knowledge(item_id: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
    """基于标签重叠推荐相关 knowledge items。

    Parameters
    ----------
    item_id:
        种子 item 的 ID。
    limit:
        最多返回条数。

    Returns
    -------
    list[dict]
        每条: ``{"item": <KnowledgeItem.to_dict()>, "score": int, "shared_tags": list[str]}``
        按 score 降序, 同分按 ingested_at 降序。
    """
    effective_limit = max(1, min(limit, _MAX_LIMIT))
    seed_tags = _get_knowledge_tags(item_id)
    if not seed_tags:
        return []

    # 取候选 items (最多 200 条最近的)
    candidates = knowledge_repo.list_items(limit=200)
    scored: list[dict] = []
    for other in candidates:
        if other.id == item_id:
            continue
        other_tags = set(other.tags or [])
        shared = seed_tags & other_tags
        if not shared:
            continue
        scored.append(
            {
                "item": other.to_dict(),
                "score": len(shared),
                "shared_tags": sorted(shared),
            }
        )

    # 排序: score 降序 → ingested_at 降序 (用 -score 保证降序, ingested_at
    # 是 ISO 字符串, 降序需取反但字符串没法取反, 所以用 reverse=True + 两次 sort)
    scored.sort(
        key=lambda x: x["item"].get("ingested_at", ""), reverse=True
    )  # ingested_at 降序 (stable)
    scored.sort(key=lambda x: x["score"], reverse=True)  # score 降序 (stable)
    return scored[:effective_limit]


def recommend_hotspot(hotspot_id: str, limit: int = _DEFAULT_LIMIT) -> list[dict]:
    """基于标签重叠推荐相关 hotspots。

    Parameters
    ----------
    hotspot_id:
        种子 hotspot 的 ID。
    limit:
        最多返回条数。

    Returns
    -------
    list[dict]
        每条: ``{"item": {id,title,summary,...}, "score": int, "shared_tags": list[str]}``
    """
    effective_limit = max(1, min(limit, _MAX_LIMIT))
    seed_tags = _get_hotspot_tags(hotspot_id)
    if not seed_tags:
        return []

    # 找所有共享至少一个标签的 hotspot (通过 hotspot_tags 关联表)
    placeholders = ",".join("?" * len(seed_tags))
    rows = get_connection().execute(
        f"""
        SELECT h.id, h.title, h.summary, h.source, h.url, h.category,
               h.ingested_at, h.score,
               GROUP_CONCAT(ht.tag_id) AS shared_tags
        FROM hotspots h
        JOIN hotspot_tags ht ON ht.hotspot_id = h.id
        WHERE ht.tag_id IN ({placeholders})
          AND h.id != ?
          AND (h.quality_flags IS NULL OR (
            h.quality_flags NOT LIKE '%historical_published%' AND
            h.quality_flags NOT LIKE '%no_published_at%'
          ))
        GROUP BY h.id
        ORDER BY COUNT(ht.tag_id) DESC, h.ingested_at DESC
        LIMIT ?
        """,
        (*seed_tags, hotspot_id, effective_limit),
    ).fetchall()

    results: list[dict] = []
    for r in rows:
        shared = r["shared_tags"].split(",") if r["shared_tags"] else []
        results.append(
            {
                "item": {
                    "id": r["id"],
                    "title": r["title"],
                    "summary": r["summary"],
                    "source": r["source"],
                    "url": r["url"],
                    "category": r["category"],
                    "ingested_at": r["ingested_at"],
                    "score": r["score"],
                },
                "score": len(shared),
                "shared_tags": sorted(set(shared) & seed_tags),
            }
        )
    return results


def recommend(
    entity_type: str, entity_id: str, limit: int = _DEFAULT_LIMIT
) -> list[dict]:
    """统一推荐入口 (跨层分发)。

    Parameters
    ----------
    entity_type:
        ``"knowledge"`` 或 ``"hotspot"``。
    entity_id:
        种子实体 ID。
    limit:
        最多返回条数。

    Returns
    -------
    list[dict]
        推荐结果列表, 每条含 ``item`` / ``score`` / ``shared_tags``。
    """
    if entity_type == "knowledge":
        return recommend_knowledge(entity_id, limit)
    if entity_type == "hotspot":
        return recommend_hotspot(entity_id, limit)
    return []


__all__ = ["recommend", "recommend_knowledge", "recommend_hotspot"]

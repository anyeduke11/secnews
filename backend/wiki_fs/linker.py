"""Concept linker — FTS/tag 共现 → 权重边 (S2-4)。

两种边发现策略:
1. **tag 共现** — 标签交集比例 ≥ min_weight 即建边
2. **title 相似** — 标题关键词交集 → related 条目 ID 列表

产出 [{source, target, weight, shared_tags?, match_type}] 供 graph.json
合并与前端知识图谱消费。
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import logger


def build_edges(wiki_fs: Any, min_weight: float = 0.5) -> list[dict]:
    """Scan all items → weighted edges based on tag co-occurrence."""
    if wiki_fs is None:
        return []

    items: list[dict] = []
    for item_id in wiki_fs.list_ids():
        doc = wiki_fs.read_item(item_id)
        if doc is None:
            continue
        tags = {t.lower() for t in doc["fm"].get("tags", [])}
        if tags:
            items.append({"id": item_id, "tags": tags})

    edges: list[dict] = []
    seen: set[frozenset] = set()
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            pair_key = frozenset([a["id"], b["id"]])
            if pair_key in seen:
                continue
            shared = a["tags"] & b["tags"]
            if not shared:
                continue
            weight = len(shared) / max(len(a["tags"]), len(b["tags"]))
            if weight >= min_weight:
                edges.append({
                    "source": a["id"],
                    "target": b["id"],
                    "weight": round(weight, 3),
                    "shared_tags": sorted(shared),
                    "match_type": "tag_cooccur",
                })
                seen.add(pair_key)

    logger.info(f"build_edges: {len(edges)} tag-cooccur edges from {len(items)} items")
    return edges


def find_related(
    db_conn: Any,
    item_id: str,
    title: str,
    tags: list[str],
    top_k: int = 10,
) -> list[str]:
    """找相关条目 ID (标题关键词 LIKE + 标签匹配, 排除自身)。

    供 kl_pipeline link 阶段调用。使用 SQL LIKE 而非 FTS5 MATCH —
    wiki_items_fts 的 tokenizer 对中文不理想, 且 LIKE 在当前规模 (<10k)
    下性能可接受。
    """
    if db_conn is None or not title:
        return []

    # 提取标题中 ≥2 字的词段作为 LIKE 模式
    keywords = [w.strip() for w in title.replace("：", " ").replace("，", " ").split() if len(w.strip()) >= 2]
    keywords.extend(str(t) for t in (tags or [])[:3] if t)
    if not keywords:
        return []

    conditions = " OR ".join(["title LIKE ?"] * min(len(keywords), 5))
    params = [f"%{kw}%" for kw in keywords[:5]]

    try:
        rows = db_conn.execute(
            f"SELECT id FROM knowledge_items "
            f"WHERE id != ? AND ({conditions}) LIMIT ?",
            [item_id, *params, top_k],
        ).fetchall()
        return [r[0] for r in rows]
    except Exception as e:
        logger.warning(f"find_related failed for {item_id}: {e}")
        return []


__all__ = ["build_edges", "find_related"]

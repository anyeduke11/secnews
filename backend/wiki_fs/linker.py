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
    wiki_fs: Any,
    item_id: str,
    title: str,
    tags: list[str],
    top_k: int = 10,
) -> list[str]:
    """找相关条目 ID (标题关键词匹配, 排除自身)。

    S2-4 修正: knowledge_items 表已按 wiki-first 哲学移除,
    改用 wiki_fs 遍历 + 标题关键词匹配。
    """
    if wiki_fs is None or not title:
        return []

    # 提取标题关键词 (≥2 字的词段 + tags)
    keywords = set()
    for w in title.replace("：", " ").replace("，", " ").replace("。", " ").split():
        w = w.strip()
        if len(w) >= 2:
            keywords.add(w.lower())
    for t in (tags or [])[:5]:
        t = str(t).strip().lower()
        if len(t) >= 2:
            keywords.add(t)
    if not keywords:
        return []

    related: list[str] = []
    for other_id in wiki_fs.list_ids():
        if other_id == item_id:
            continue
        doc = wiki_fs.read_item(other_id)
        if doc is None:
            continue
        other_title = str(doc["fm"].get("title") or "").lower()
        other_tags = {str(t).lower() for t in doc["fm"].get("tags", [])}
        for kw in keywords:
            if kw in other_title or kw in other_tags:
                related.append(other_id)
                break
        if len(related) >= top_k:
            break

    return related


__all__ = ["build_edges", "find_related"]

"""Concept linker — builds weighted edges from FTS co-occurrence.

Scans items for shared tags and title terms to produce a weighted
edge list suitable for graph visualization.
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import logger


def build_edges(wiki_fs: Any, min_weight: float = 0.5) -> list[dict]:
    """Scan all items and produce weighted edges based on tag co-occurrence.

    Returns:
        [{"source": id1, "target": id2, "weight": float}, ...]
    """
    if wiki_fs is None:
        return []

    items: list[dict] = []
    for item_id in wiki_fs.list_ids():
        doc = wiki_fs.read_item(item_id)
        if doc is None:
            continue
        tags = set(t.lower() for t in doc["fm"].get("tags", []))
        if tags:
            items.append({"id": item_id, "tags": tags})

    edges: list[dict] = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
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
                })

    logger.info(f"build_edges: {len(edges)} edges from {len(items)} items")
    return edges

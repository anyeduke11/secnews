"""Graph builder — construct knowledge graph from concepts + items.

Nodes: knowledge_concepts (count = len(source_items))
Edges: concept co-occurrence in knowledge_items.concepts
Cache: knowledge_graph table, 5-minute TTL
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.repository.db import get_connection
from backend.repository.knowledge_repo import knowledge_repo

log = logging.getLogger("hotspot.graph_builder")

CACHE_TTL_MINUTES = 5


def build_graph(domain: Optional[str] = None, include_local: bool = True) -> dict:
    """Build knowledge graph {nodes, edges}.

    Args:
        domain: optional domain filter
        include_local: if True and local wiki is available, merge local nodes

    Returns: {"nodes": [...], "edges": [...]}
    """
    # Check cache
    cached = _get_cached_graph()
    if cached and _cache_fresh(cached, CACHE_TTL_MINUTES):
        graph = json.loads(cached["graph_data"])
        if domain:
            graph = _filter_by_domain(graph, domain)
        if include_local:
            graph = _merge_local(graph, domain)
        return graph

    # Build nodes from concepts
    concepts = knowledge_repo.list_concepts(domain=domain)
    nodes = [
        {
            "id": c.slug,
            "label": c.title,
            "domain": c.domain,
            "count": len(c.source_items),
            "wiki": "hotspot",
            "type": "concept",
        }
        for c in concepts
    ]

    # Build edges from concept co-occurrence
    edges = _build_edges(domain)

    graph = {"nodes": nodes, "edges": edges}
    _save_graph_cache(graph)
    if include_local:
        graph = _merge_local(graph, domain)
    return graph


def _merge_local(graph: dict, domain: Optional[str]) -> dict:
    """Merge local wiki nodes + federated edges into graph (no-op if unavailable)."""
    from backend.services.federation_service import merge_graph
    return merge_graph(graph, domain=domain)


def _build_edges(domain: Optional[str] = None) -> list[dict]:
    """Build edges from concept co-occurrence in items."""
    conn = get_connection()
    if domain:
        rows = conn.execute(
            "SELECT concepts FROM knowledge_items WHERE domain = ?",
            (domain,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT concepts FROM knowledge_items"
        ).fetchall()

    edge_map: dict[tuple[str, str], int] = {}
    for row in rows:
        concepts_raw = row[0] if row[0] else "[]"
        try:
            concepts = json.loads(concepts_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(concepts, list) or len(concepts) < 2:
            continue
        for i, c1 in enumerate(concepts):
            for c2 in concepts[i + 1:]:
                key = tuple(sorted([str(c1), str(c2)]))
                edge_map[key] = edge_map.get(key, 0) + 1

    return [
        {"source": k[0], "target": k[1], "weight": v, "type": "related"}
        for k, v in edge_map.items()
    ]


def _get_cached_graph() -> Optional[dict]:
    """Get latest cached graph from knowledge_graph table."""
    conn = get_connection()
    row = conn.execute(
        "SELECT graph_data, updated_at FROM knowledge_graph ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {"graph_data": row[0], "updated_at": row[1]}


def _cache_fresh(cached: dict, ttl_minutes: int) -> bool:
    """Check if cached graph is within TTL."""
    try:
        updated_str = cached["updated_at"]
        # Handle ISO 8601 with timezone
        if "+" in updated_str and not updated_str.endswith("Z"):
            updated = datetime.fromisoformat(updated_str)
        elif updated_str.endswith("Z"):
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
        else:
            # Fallback: assume UTC
            updated = datetime.fromisoformat(updated_str).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return now - updated < timedelta(minutes=ttl_minutes)
    except (ValueError, TypeError) as e:
        log.warning(f"cache freshness check failed: {e}")
        return False


def _filter_by_domain(graph: dict, domain: str) -> dict:
    """Filter graph to only include nodes/edges in specified domain."""
    node_ids = {n["id"] for n in graph["nodes"] if n.get("domain") == domain}
    return {
        "nodes": [n for n in graph["nodes"] if n.get("domain") == domain],
        "edges": [
            e for e in graph["edges"]
            if e["source"] in node_ids and e["target"] in node_ids
        ],
    }


def _save_graph_cache(graph: dict) -> None:
    """Save graph to knowledge_graph table."""
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO knowledge_graph (graph_data, updated_at) VALUES (?, ?)",
        (json.dumps(graph), now),
    )

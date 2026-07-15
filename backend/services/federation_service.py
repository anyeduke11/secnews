"""Federation service — local wiki federation + graph merge.

Reads local LLM-Wiki at config.local_wiki_path (default ~/knowledge-base).
- concepts: 02-知识库/*.md (frontmatter: slug/title/domain)
- items: 01-资料库/*.md (frontmatter: id/title/domain)

All operations are readonly when config.local_wiki_readonly=True.
Gracefully degrades when local_wiki_enabled=False or path missing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from backend.config import config
from backend.services.knowledge_sync import parse_frontmatter

log = logging.getLogger("hotspot.federation")

DEFAULT_LOCAL_WIKI_PATH = "~/knowledge-base"
LOCAL_CONCEPTS_DIR = "02-知识库"
LOCAL_ITEMS_DIR = "01-资料库"


def _local_wiki_root() -> Path:
    """Resolve local wiki root path, expanding ~."""
    raw = config.local_wiki_path or DEFAULT_LOCAL_WIKI_PATH
    return Path(raw).expanduser()


def _is_available() -> bool:
    """Check if local wiki federation is enabled and path exists."""
    if not config.local_wiki_enabled:
        return False
    return _local_wiki_root().exists()


def list_local_concepts() -> list[dict]:
    """Scan local wiki concepts dir (02-知识库/*.md), parse frontmatter.

    Returns list of dicts with slug/title/domain. Empty list if unavailable.
    """
    if not _is_available():
        return []
    concepts_dir = _local_wiki_root() / LOCAL_CONCEPTS_DIR
    if not concepts_dir.exists():
        return []
    results: list[dict] = []
    for md_path in concepts_dir.glob("*.md"):
        fm = parse_frontmatter(md_path)
        if fm is None:
            continue
        results.append({
            "slug": fm.get("slug", md_path.stem),
            "title": fm.get("title", md_path.stem),
            "domain": fm.get("domain"),
        })
    return results


def list_local_items() -> list[dict]:
    """Scan local wiki items dir (01-资料库/*.md), parse frontmatter.

    Returns list of dicts with id/title/domain. Empty list if unavailable.
    """
    if not _is_available():
        return []
    items_dir = _local_wiki_root() / LOCAL_ITEMS_DIR
    if not items_dir.exists():
        return []
    results: list[dict] = []
    for md_path in items_dir.glob("*.md"):
        fm = parse_frontmatter(md_path)
        if fm is None:
            continue
        results.append({
            "id": fm.get("id", md_path.stem),
            "title": fm.get("title", md_path.stem),
            "domain": fm.get("domain"),
        })
    return results


def get_federation_status() -> dict:
    """Return federation status dict.

    Degrades gracefully when disabled or path missing.
    """
    root = _local_wiki_root()
    enabled = config.local_wiki_enabled
    exists = root.exists() if enabled else False

    if not enabled or not exists:
        return {
            "local_wiki_enabled": enabled,
            "local_wiki_path": str(root),
            "local_wiki_exists": exists,
            "local_concepts_count": 0,
            "local_items_count": 0,
            "federated_edges": 0,
            "readonly": config.local_wiki_readonly,
        }

    concepts = list_local_concepts()
    items = list_local_items()
    federated_edges = _count_federated_edges(concepts)

    return {
        "local_wiki_enabled": True,
        "local_wiki_path": str(root),
        "local_wiki_exists": True,
        "local_concepts_count": len(concepts),
        "local_items_count": len(items),
        "federated_edges": federated_edges,
        "readonly": config.local_wiki_readonly,
    }


def _count_federated_edges(local_concepts: list[dict]) -> int:
    """Count federated edges that would be created.

    Federated edge: hotspot concept.slug == local concept.slug.
    """
    if not local_concepts:
        return 0
    local_slugs = {c["slug"] for c in local_concepts if c.get("slug")}
    if not local_slugs:
        return 0
    from backend.repository.knowledge_repo import knowledge_repo
    hotspot_concepts = knowledge_repo.list_concepts()
    hotspot_slugs = {c.slug for c in hotspot_concepts}
    return len(local_slugs & hotspot_slugs)


def merge_graph(hotspot_graph: dict, domain: Optional[str] = None) -> dict:
    """Merge hotspot graph with local wiki nodes + federated edges.

    - Local concept nodes: id="local:{slug}", wiki="local"
    - Federated edges: hotspot.slug == local.slug, type="federated"

    Args:
        hotspot_graph: {"nodes": [...], "edges": [...]} from hotspot wiki
        domain: optional domain filter applied to local nodes

    Returns merged graph {nodes, edges}. Returns hotspot_graph unchanged
    if local wiki is unavailable.
    """
    if not _is_available():
        return hotspot_graph

    local_concepts = list_local_concepts()
    if not local_concepts:
        return hotspot_graph

    # Apply domain filter to local concepts if specified
    if domain:
        local_concepts = [
            c for c in local_concepts
            if c.get("domain") == domain or c.get("domain") is None
        ]

    existing_nodes = hotspot_graph.get("nodes", [])
    existing_edges = hotspot_graph.get("edges", [])
    existing_ids = {n["id"] for n in existing_nodes}

    # Hotspot node IDs (slugs) for federated edge matching
    hotspot_node_ids = {
        n["id"] for n in existing_nodes if n.get("wiki") == "hotspot"
    }

    # Add local concept nodes
    new_nodes: list[dict] = []
    for c in local_concepts:
        slug = c.get("slug")
        if not slug:
            continue
        node_id = f"local:{slug}"
        if node_id in existing_ids:
            continue
        new_nodes.append({
            "id": node_id,
            "label": c.get("title", slug),
            "domain": c.get("domain"),
            "count": 0,
            "wiki": "local",
        })

    # Build federated edges: hotspot.slug == local.slug
    new_edges: list[dict] = []
    for c in local_concepts:
        slug = c.get("slug")
        if not slug:
            continue
        if slug in hotspot_node_ids:
            new_edges.append({
                "source": slug,
                "target": f"local:{slug}",
                "weight": 1,
                "type": "federated",
            })

    return {
        "nodes": existing_nodes + new_nodes,
        "edges": existing_edges + new_edges,
    }

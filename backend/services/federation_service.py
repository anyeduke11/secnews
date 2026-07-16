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

# Hotspot knowledge 目录（项目根 /knowledge）
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"


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

    Phase 1f Task 6.11: 同时回填 hotspot concept 的 local_wiki_ref。
    当 local.slug == hotspot.slug 且 local_wiki_ref 为空时写入。
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

    # Task 6.11: 回填 hotspot concept 的 local_wiki_ref
    if results:
        try:
            from backend.repository.knowledge_repo import knowledge_repo
            local_slugs = {c["slug"] for c in results if c.get("slug")}
            if local_slugs:
                hotspot_concepts = knowledge_repo.list_concepts()
                for c in hotspot_concepts:
                    if c.slug in local_slugs and not c.local_wiki_ref:
                        ref = f"wiki:local:concepts/{c.slug}"
                        knowledge_repo.update_concept_local_wiki_ref(c.slug, ref)
                        log.info(f"backfilled local_wiki_ref for concept: {c.slug}")
        except Exception as e:
            log.warning(f"local_wiki_ref backfill failed (ignored): {e}")

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


def migrate_high_mastery_items() -> dict:
    """Phase 1f Task 6.10: 迁移高掌握度条目（mastery > 80）到本地 wiki 02-知识库。

    - 查询 knowledge_items WHERE mastery > 80
    - 复制 .md 到 {local_wiki_path}/02-知识库/{id}.md
    - 在原条目 frontmatter 追加 migrated_to_local: true
    - local_wiki_path 不存在时降级跳过
    - knowledge_items 表无 migrated_to_local 列，故只更新 .md
    """
    import shutil
    from backend.repository.db import get_connection

    raw_path = config.local_wiki_path or ""
    if not raw_path:
        log.info("migrate_high_mastery_items: local_wiki_path empty, skipping")
        return {"migrated": 0, "skipped": 0}

    local_root = Path(raw_path).expanduser()
    if not local_root.exists():
        log.info(
            f"migrate_high_mastery_items: local_wiki_path {local_root} does not exist, skipping"
        )
        return {"migrated": 0, "skipped": 0}

    target_dir = local_root / LOCAL_CONCEPTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    hotspot_items_dir = KNOWLEDGE_DIR / "items"

    conn = get_connection()
    rows = conn.execute(
        "SELECT id FROM knowledge_items WHERE mastery > 80"
    ).fetchall()

    migrated = 0
    skipped = 0
    for row in rows:
        item_id = row["id"]
        src_path = hotspot_items_dir / f"{item_id}.md"
        if not src_path.exists():
            log.warning(f"migrate: source .md not found for item {item_id}, skipping")
            skipped += 1
            continue
        try:
            dst_path = target_dir / f"{item_id}.md"
            shutil.copy2(src_path, dst_path)

            # 在原条目 frontmatter 追加 migrated_to_local: true
            content = src_path.read_text(encoding="utf-8")
            if "migrated_to_local:" not in content:
                new_content = content.replace(
                    "\n---\n", "\nmigrated_to_local: true\n---\n", 1
                )
                src_path.write_text(new_content, encoding="utf-8")

            migrated += 1
            log.info(f"migrated item {item_id} to {dst_path}")
        except Exception as e:
            log.warning(f"migrate item {item_id} failed (ignored): {e}")
            skipped += 1

    log.info(f"migrate_high_mastery_items: {migrated} migrated, {skipped} skipped")
    return {"migrated": migrated, "skipped": skipped}

"""kl:link stage — concept linking via tag co-occurrence + title LIKE (S2-4).

Scans the item's tags and title against the concept index and other
items to build related-edges in the frontmatter.
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import logger
from backend.wiki_fs.contract import get_lifecycle


def _get_db_conn() -> Any:
    """Lazy import to avoid circular dependency at module load."""
    from backend.repository.db import get_connection
    return get_connection()


def run_link(item_id: str, wiki_fs: Any, llm_client: Any) -> None:
    """Link an item to related concepts and items."""
    doc = wiki_fs.read_item(item_id)
    if doc is None:
        raise ValueError(f"item not found: {item_id}")

    fm = doc["fm"]
    if get_lifecycle(fm) != "kl:refine":
        logger.info(f"link: skipping {item_id} (stage={get_lifecycle(fm)})")
        return

    # S2-4: concept-linker — find_related (标题 LIKE + 标签) + FTS fallback。
    related: list[str] = []
    try:
        from backend.wiki_fs.linker import find_related
        related = find_related(
            db_conn=_get_db_conn(),
            item_id=item_id,
            title=str(fm.get("title") or ""),
            tags=fm.get("tags", []),
            top_k=10,
        )
    except Exception as exc:
        logger.warning(f"link: find_related failed for {item_id}: {exc}")
        try:
            raw = wiki_fs.find_related(item_id, top_k=10)
            related = [r["id"] if isinstance(r, dict) else str(r) for r in raw]
        except Exception:
            pass

    # Match concept slugs from tags.
    concepts = []
    try:
        all_concepts = wiki_fs.list_concepts()
        tag_set = {t.lower() for t in fm.get("tags", [])}
        for c in all_concepts:
            if c.get("name", "").lower() in tag_set:
                concepts.append(c["id"])
    except Exception:
        pass

    fm["related"] = related[:10]
    fm["concept_links"] = concepts
    fm["lifecycle"] = "kl:link"
    wiki_fs.write_item(item_id, {"fm": fm, "body": doc.get("body", "")})

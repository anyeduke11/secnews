"""Map updater — regenerate knowledge/_MAP.md after compilation."""
from __future__ import annotations

import logging
from pathlib import Path

from backend.domain.knowledge_models import now_iso
from backend.repository.knowledge_repo import knowledge_repo

log = logging.getLogger("hotspot.map_updater")

MAP_PATH = Path(__file__).resolve().parent.parent.parent / "knowledge" / "_MAP.md"

VALID_DOMAINS = [
    "security", "ai", "finance", "product",
    "engineering", "business", "design", "other",
]
VALID_TYPES = [
    "news", "analysis", "paper", "tutorial",
    "tool", "opinion", "case-study", "report",
]
VALID_DIFFICULTY = ["beginner", "intermediate", "advanced", "expert"]


def _render_items_index(items: list) -> str:
    """Group items by domain, render as markdown list."""
    by_domain: dict[str, list] = {}
    for item in items:
        domain = item.domain or "uncategorized"
        by_domain.setdefault(domain, []).append(item)

    lines: list[str] = []
    for domain in VALID_DOMAINS + (["uncategorized"] if "uncategorized" in by_domain else []):
        if domain not in by_domain:
            continue
        domain_items = by_domain[domain]
        lines.append(f"\n### {domain} ({len(domain_items)})\n")
        for item in sorted(domain_items, key=lambda i: i.id):
            mark = "x" if item.compiled else " "
            topic = item.topic or "-"
            lines.append(f"- [{mark}] `{item.id}` ({topic}) — {item.title}")
    return "\n".join(lines)


def _render_concepts_index(concepts: list) -> str:
    """Group concepts by domain, render as markdown list."""
    by_domain: dict[str, list] = {}
    for concept in concepts:
        domain = concept.domain or "uncategorized"
        by_domain.setdefault(domain, []).append(concept)

    lines: list[str] = []
    for domain in VALID_DOMAINS + (["uncategorized"] if "uncategorized" in by_domain else []):
        if domain not in by_domain:
            continue
        domain_concepts = by_domain[domain]
        lines.append(f"\n### {domain} ({len(domain_concepts)})\n")
        for concept in sorted(domain_concepts, key=lambda c: c.slug):
            count = len(concept.source_items)
            lines.append(f"- `{concept.slug}` ({count} items) — {concept.title}")
    return "\n".join(lines)


def update_map() -> dict:
    """Regenerate _MAP.md with current statistics + items/concepts index."""
    items = knowledge_repo.list_items(limit=100000)
    concepts = knowledge_repo.list_concepts()
    total = len(items)
    compiled = sum(1 for i in items if i.compiled)
    ratio = (compiled / total * 100) if total > 0 else 0

    items_index = _render_items_index(items)
    concepts_index = _render_concepts_index(concepts)

    content = f"""# Knowledge Map

> Auto-generated index. Updated by Agent after each compilation.

## Valid Domains
{', '.join(VALID_DOMAINS)}

## Valid Types
{', '.join(VALID_TYPES)}

## Difficulty Levels
{', '.join(VALID_DIFFICULTY)}

## Statistics
- Total items: {total}
- Total concepts: {len(concepts)}
- Compiled: {ratio:.1f}%
- Last compiled: {now_iso()}

## Items Index
> `[x]` = compiled, `[ ]` = pending. Grouped by domain.

{items_index}

## Concepts Index
> Grouped by domain. Count = source_items count.

{concepts_index}
"""
    MAP_PATH.write_text(content, encoding="utf-8")
    log.info(f"_MAP.md updated: {total} items, {len(concepts)} concepts")
    return {
        "total_items": total,
        "total_concepts": len(concepts),
        "compiled_ratio": ratio,
    }

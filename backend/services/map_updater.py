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


def update_map() -> dict:
    """Regenerate _MAP.md with current statistics."""
    items = knowledge_repo.list_items(limit=100000)
    concepts = knowledge_repo.list_concepts()
    total = len(items)
    compiled = sum(1 for i in items if i.compiled)
    ratio = (compiled / total * 100) if total > 0 else 0

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
"""
    MAP_PATH.write_text(content, encoding="utf-8")
    log.info(f"_MAP.md updated: {total} items, {len(concepts)} concepts")
    return {
        "total_items": total,
        "total_concepts": len(concepts),
        "compiled_ratio": ratio,
    }

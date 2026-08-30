"""Map updater — regenerate _MAP.md after compilation.

v0.6.3 P3-4: 旧 ``knowledge/_MAP.md`` 已被 ``wiki_stats_service`` + 前端
``/api/knowledge/items`` 实时接口取代。``update_map()`` 仍可调用 (写至
``llm-wiki-2.0/_MAP.md``, 旧根下线), 但 ``knowledge_watcher`` 不再自动
触发, 仅供运维偶发手动导出。推荐直接删除本模块; 当前保留以避免破坏现有
``import update_map`` 调用方 (迁移期内可能仍有 reviewer 脚本)。
"""
from __future__ import annotations

import logging

from backend.domain.knowledge_models import now_iso
from backend.repository.knowledge_repo import knowledge_repo
from backend.wiki_fs.paths import wiki_root

log = logging.getLogger("hotspot.map_updater")

# 新位置: llm-wiki-2.0/_MAP.md (旧 knowledge/_MAP.md 已下线)
MAP_PATH = wiki_root() / "_MAP.md"

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
    """Group items by domain, render as markdown list.

    Includes ALL domains (even those outside VALID_DOMAINS) so no items
    are silently dropped from the index.
    """
    by_domain: dict[str, list] = {}
    for item in items:
        domain = item.domain or "uncategorized"
        by_domain.setdefault(domain, []).append(item)

    lines: list[str] = []
    # Sort: valid domains first (in canonical order), then extras alphabetically
    valid_seen = [d for d in VALID_DOMAINS if d in by_domain]
    extras = sorted(d for d in by_domain if d not in VALID_DOMAINS and d != "uncategorized")
    uncategorized = ["uncategorized"] if "uncategorized" in by_domain else []
    for domain in valid_seen + extras + uncategorized:
        domain_items = by_domain[domain]
        lines.append(f"\n### {domain} ({len(domain_items)})\n")
        for item in sorted(domain_items, key=lambda i: i.id):
            mark = "x" if item.compiled else " "
            topic = item.topic or "-"
            lines.append(f"- [{mark}] `{item.id}` ({topic}) — {item.title}")
    return "\n".join(lines)


def _render_concepts_index(concepts: list) -> str:
    """Group concepts by domain, render as markdown list.

    Includes ALL domains (even those outside VALID_DOMAINS) so no concepts
    are silently dropped from the index.
    """
    by_domain: dict[str, list] = {}
    for concept in concepts:
        domain = concept.domain or "uncategorized"
        by_domain.setdefault(domain, []).append(concept)

    lines: list[str] = []
    valid_seen = [d for d in VALID_DOMAINS if d in by_domain]
    extras = sorted(d for d in by_domain if d not in VALID_DOMAINS and d != "uncategorized")
    uncategorized = ["uncategorized"] if "uncategorized" in by_domain else []
    for domain in valid_seen + extras + uncategorized:
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

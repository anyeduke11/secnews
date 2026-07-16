"""Cubox sync service — sync cubox cards to knowledge/items/*.md.

Design notes
------------
- ``knowledge/`` lives at the project root (parent.parent.parent of this
  file: services/ → backend/ → project root).
- Falls back gracefully when ``cubox-cli`` is not installed (returns 0).
- Item IDs are derived from URL fingerprints via ``item_id_from_url``,
  so re-syncing the same card is idempotent (existing files are skipped).
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from backend.domain.knowledge_models import KnowledgeItem, now_iso
from backend.services.data_cleaning import find_similar_items, item_id_from_url

log = logging.getLogger("hotspot.cubox_sync")

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"
ITEMS_DIR = KNOWLEDGE_DIR / "items"


def _check_cubox_cli() -> bool:
    """Check if cubox-cli is installed."""
    try:
        result = subprocess.run(
            ["cubox-cli", "version"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def fetch_cubox_cards(limit: int = 100) -> list[dict]:
    """Fetch cards from cubox-cli.

    Returns list of dicts with keys: title, url, description, tags, create_time
    """
    if not _check_cubox_cli():
        log.warning("cubox-cli not installed, skipping cubox sync")
        return []

    try:
        result = subprocess.run(
            ["cubox-cli", "card", "list", "-o", "json", "--all", "--limit", str(limit)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            log.error(f"cubox-cli failed: {result.stderr}")
            return []
        cards = json.loads(result.stdout)
        if not isinstance(cards, list):
            log.error(
                f"cubox-cli returned non-list JSON: {type(cards).__name__}"
            )
            return []
        log.info(f"cubox-cli returned {len(cards)} cards")
        return cards
    except subprocess.TimeoutExpired:
        log.error("cubox-cli timed out")
        return []
    except json.JSONDecodeError as e:
        log.error(f"cubox-cli JSON parse error: {e}")
        return []
    except Exception as e:
        log.error(f"cubox-cli unexpected error: {e}")
        return []


def _card_to_item(card: dict) -> Optional[KnowledgeItem]:
    """Convert a cubox card to a KnowledgeItem."""
    url = card.get("url", "")
    if not url:
        return None
    item_id = item_id_from_url(url)
    # Prefer article_title (full title) over title (may be truncated).
    title = card.get("article_title") or card.get("title") or "Untitled"
    # Normalize tags: cubox returns list of tag objects or strings.
    raw_tags = card.get("tags", [])
    if isinstance(raw_tags, list):
        tags = [
            t.get("name", "") if isinstance(t, dict) else str(t)
            for t in raw_tags
        ]
        tags = [t for t in tags if t]
    else:
        tags = []
    return KnowledgeItem(
        id=item_id,
        title=title,
        source="cubox",
        source_url=url,
        tags=tags,
        ingested_at=card.get("create_time", now_iso()),
        updated_at=card.get("update_time", now_iso()),
    )


def _write_item_md(item: KnowledgeItem, content: str = "", sources: list[str] | None = None) -> Path:
    """Write a knowledge item to knowledge/items/{id}.md."""
    if sources is None:
        sources = ["cubox"]
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    path = ITEMS_DIR / f"{item.id}.md"

    frontmatter = f"""---
id: "{item.id}"
title: "{item.title}"
source: "{item.source}"
source_url: "{item.source_url}"
ingested_at: "{item.ingested_at}"
compiled: false
domain: null
topic: null
type: null
difficulty: null
tags: {json.dumps(item.tags)}
concepts: []
mastery: 0
last_reviewed: null
review_count: 0
related_items: []
sources: {json.dumps(sources)}
---

# {item.title}

{content}
"""
    path.write_text(frontmatter, encoding="utf-8")
    return path


def sync_cubox_to_knowledge(limit: int = 100) -> int:
    """Sync cubox cards to knowledge/items/*.md.

    Returns number of items written or merged.
    """
    from backend.repository.knowledge_repo import knowledge_repo
    from backend.services.knowledge_sync import parse_frontmatter

    cards = fetch_cubox_cards(limit)
    if not cards:
        return 0

    count = 0
    for card in cards:
        item = _card_to_item(card)
        if item is None:
            continue

        content = card.get("description", "") or ""
        md_path = ITEMS_DIR / f"{item.id}.md"

        if md_path.exists():
            # Item exists — merge sources + tags (don't reset classification)
            existing_fm = parse_frontmatter(md_path) or {}
            existing_sources = (
                existing_fm.get("sources", [])
                if isinstance(existing_fm.get("sources"), list)
                else ["cubox"]
            )
            existing_tags = (
                existing_fm.get("tags", [])
                if isinstance(existing_fm.get("tags"), list)
                else []
            )
            merged_sources = list(dict.fromkeys(existing_sources + ["cubox"]))
            merged_tags = list(dict.fromkeys(existing_tags + item.tags))

            # Update .md frontmatter (sources + tags) preserving body
            _update_md_frontmatter(md_path, merged_sources, merged_tags)

            # Update SQLite tags only (sources not in DB schema)
            existing_item = knowledge_repo.get_item(item.id)
            if existing_item:
                existing_item.tags = merged_tags
                existing_item.updated_at = now_iso()
                knowledge_repo.upsert_item(existing_item)
            count += 1
        else:
            # New item — check for similar URLs
            if item.source_url:
                similar = find_similar_items(item.source_url)
                if similar:
                    for sid in similar:
                        item.tags.append(f"similar:{sid}")
                    log.info(
                        "similar URLs found for %s: %s", item.id, similar
                    )
            _write_item_md(item, content, sources=["cubox"])
            knowledge_repo.upsert_item(item)
            count += 1

    log.info(f"cubox sync: {count} items written/merged")
    return count


def _update_md_frontmatter(
    path: Path, sources: list[str], tags: list[str]
) -> None:
    """Update sources + tags lines in .md frontmatter, preserving body."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return
    parts = text.split("---", 2)
    if len(parts) < 3:
        return
    frontmatter = parts[1]
    body = parts[2]

    import re

    # Replace or add sources line
    if re.search(r"^sources:", frontmatter, re.MULTILINE):
        frontmatter = re.sub(
            r"^sources:.*$",
            f"sources: {json.dumps(sources)}",
            frontmatter,
            flags=re.MULTILINE,
        )
    else:
        frontmatter = frontmatter.rstrip() + f"\nsources: {json.dumps(sources)}\n"

    # Replace tags line
    if re.search(r"^tags:", frontmatter, re.MULTILINE):
        frontmatter = re.sub(
            r"^tags:.*$",
            f"tags: {json.dumps(tags)}",
            frontmatter,
            flags=re.MULTILINE,
        )

    path.write_text(f"---{frontmatter}---{body}", encoding="utf-8")

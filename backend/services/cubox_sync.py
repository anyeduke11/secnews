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
from backend.services.data_cleaning import item_id_from_url

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


def _write_item_md(item: KnowledgeItem, content: str = "") -> Path:
    """Write a knowledge item to knowledge/items/{id}.md."""
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
---

# {item.title}

{content}
"""
    path.write_text(frontmatter, encoding="utf-8")
    return path


def sync_cubox_to_knowledge(limit: int = 100) -> int:
    """Sync cubox cards to knowledge/items/*.md.

    Returns number of new items written.
    """
    cards = fetch_cubox_cards(limit)
    if not cards:
        return 0

    existing = set()
    if ITEMS_DIR.exists():
        existing = {f.stem for f in ITEMS_DIR.glob("*.md")}

    count = 0
    for card in cards:
        item = _card_to_item(card)
        if item is None or item.id in existing:
            continue
        # Cubox card fields: description (summary), article_title (full title).
        # Full article content is not returned by card list; description is
        # the card's note/summary.
        content = card.get("description", "") or ""
        _write_item_md(item, content)
        existing.add(item.id)
        count += 1

    log.info(f"cubox sync: {count} new items written")
    return count

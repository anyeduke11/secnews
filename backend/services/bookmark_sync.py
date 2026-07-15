"""Bookmark import service — parse Chrome/Edge bookmarks JSON, dedup, write to knowledge/items/."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from backend.domain.knowledge_models import KnowledgeItem, now_iso
from backend.repository.knowledge_repo import knowledge_repo
from backend.services.data_cleaning import (
    clean_and_dedupe,
    item_id_from_url,
    url_fingerprint,
    validate_url,
)

log = logging.getLogger("hotspot.bookmark_sync")

ITEMS_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge" / "items"


def parse_chrome_bookmarks(node: dict, folder_tags: Optional[list[str]] = None) -> list[dict]:
    """Recursively parse Chrome/Edge bookmarks JSON.
    
    Returns list of {url, title, tags} dicts.
    folder_tags: accumulated ancestor folder names (used as tags).
    """
    if folder_tags is None:
        folder_tags = []
    
    results: list[dict] = []
    node_type = node.get("type", "")
    node_name = node.get("name", "")
    
    if node_type == "url":
        url = node.get("url", "")
        if url:
            results.append({
                "url": url,
                "title": node_name or url,
                "tags": list(folder_tags),
            })
    elif node_type == "folder" or "children" in node:
        # Recurse into children, passing folder name as tag
        new_tags = folder_tags + ([node_name] if node_name else [])
        for child in node.get("children", []):
            results.extend(parse_chrome_bookmarks(child, new_tags))
    elif "children" in node:
        # Root node or unnamed folder
        for child in node.get("children", []):
            results.extend(parse_chrome_bookmarks(child, folder_tags))
    
    return results


def _write_bookmark_md(item: KnowledgeItem, tags: list[str], content: str = "") -> Path:
    """Write a bookmark item to knowledge/items/{id}.md."""
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    path = ITEMS_DIR / f"{item.id}.md"
    
    frontmatter = f"""---
id: "{item.id}"
title: "{item.title}"
source: "bookmark"
source_url: "{item.source_url}"
ingested_at: "{item.ingested_at}"
compiled: false
domain: null
topic: null
type: null
difficulty: null
tags: {json.dumps(tags)}
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


def import_bookmarks(items: list[dict], validate: bool = False) -> dict:
    """Import parsed bookmarks into knowledge base.
    
    Args:
        items: list of {url, title, tags} dicts
        validate: if True, validate URLs via proxy (slow)
    
    Returns: {imported, skipped_duplicates, skipped_invalid, dead_links}
    """
    # Internal dedup first (same URL multiple times, merge tags)
    seen: dict[str, dict] = {}
    for item in items:
        url = item.get("url", "")
        if not url:
            continue
        fp = url_fingerprint(url)
        if fp in seen:
            # Merge tags
            existing_tags = set(seen[fp].get("tags", []))
            existing_tags.update(item.get("tags", []))
            seen[fp]["tags"] = list(existing_tags)
        else:
            seen[fp] = dict(item)
    
    imported = 0
    skipped_duplicates = 0
    skipped_invalid = 0
    dead_links = 0
    
    for fp, item in seen.items():
        url = item["url"]
        title = item.get("title", "Untitled")
        tags = item.get("tags", [])
        
        # Generate item ID
        item_id = item_id_from_url(url)
        
        # Check if already exists in DB
        existing = knowledge_repo.get_item(item_id)
        if existing:
            skipped_duplicates += 1
            continue
        
        # Optional URL validation
        is_dead = False
        if validate:
            if not validate_url(url):
                is_dead = True
                dead_links += 1
                tags = tags + ["dead_link"]
        
        # Create KnowledgeItem
        now = now_iso()
        ki = KnowledgeItem(
            id=item_id,
            title=title,
            source="bookmark",
            source_url=url,
            tags=tags,
            ingested_at=now,
            updated_at=now,
        )
        
        # Write .md file
        _write_bookmark_md(ki, tags)
        
        # Sync to SQLite
        knowledge_repo.upsert_item(ki)
        imported += 1
        log.debug(f"imported bookmark: {item_id} ({title})")
    
    log.info(f"bookmark import: {imported} new, {skipped_duplicates} dup, {dead_links} dead")
    return {
        "imported": imported,
        "skipped_duplicates": skipped_duplicates,
        "skipped_invalid": skipped_invalid,
        "dead_links": dead_links,
    }

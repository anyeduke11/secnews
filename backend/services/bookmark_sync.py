"""Bookmark import service — parse Chrome/Edge bookmarks JSON, dedup, write to knowledge/items/."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from backend.domain.knowledge_models import KnowledgeItem, now_iso
from backend.repository.knowledge_repo import knowledge_repo
from backend.services.data_cleaning import (
    clean_and_dedupe,
    find_similar_items,
    item_id_from_url,
    url_fingerprint,
    validate_url,
)

log = logging.getLogger("hotspot.bookmark_sync")

ITEMS_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge" / "items"


def parse_chrome_bookmarks(node: dict | list, folder_tags: Optional[list[str]] = None) -> list[dict]:
    """Recursively parse Chrome/Edge bookmarks JSON.

    Returns list of {url, title, tags} dicts.
    folder_tags: accumulated ancestor folder names (used as tags).

    Accepts:
    - Chrome root JSON: ``{"roots": {"bookmark_bar": {...}, "other": {...}}}``
    - A single folder/url node: ``{"type": "folder", "children": [...]}``
    - A list of nodes: ``[{...}, {...}]``
    """
    if folder_tags is None:
        folder_tags = []

    results: list[dict] = []

    # Chrome root format: {"roots": {...}, "version": "1"} — iterate root folders
    if isinstance(node, dict) and "roots" in node and "type" not in node:
        roots = node.get("roots") or {}
        if isinstance(roots, dict):
            for child in roots.values():
                if isinstance(child, dict):
                    results.extend(parse_chrome_bookmarks(child, folder_tags))
        return results

    # List of nodes — iterate and merge
    if isinstance(node, list):
        for child in node:
            if isinstance(child, dict):
                results.extend(parse_chrome_bookmarks(child, folder_tags))
        return results

    if not isinstance(node, dict):
        return results

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

    return results


# Phase 1i Task 9.12: Chrome HTML export parser
# Chrome/Edge bookmarks export format:
#   <DT><A HREF="..." ADD_DATE="..." ICON="...">title</A>
#   <DT><H3 ADD_DATE="..." LAST_MODIFIED="...">folder</H3>
#   <DL><p> ... </DL><p>
# H3 folder names become tags for nested urls.
_HREF_RE = re.compile(
    r'<A\s+[^>]*HREF="([^"]+)"[^>]*>(.*?)</A>',
    re.IGNORECASE | re.DOTALL,
)
_H3_RE = re.compile(r'<H3[^>]*>(.*?)</H3>', re.IGNORECASE | re.DOTALL)


def parse_chrome_html(content: str) -> list[dict]:
    """Parse a Chrome/Edge bookmarks HTML export file.

    Returns list of {url, title, tags} dicts. Folder names (H3) enclosing
    a link become tags. The parser is intentionally regex-based (no
    html.parser dependency) — Chrome's export format is stable and
    well-formed.

    Strategy: walk the file line-by-line, maintain a folder stack. Push
    on ``<H3>`` (after closing any prior sibling folder via ``</DL>``),
    pop on ``</DL>``. Each ``<DT><A HREF>`` emits a bookmark with the
    current folder stack as tags.
    """
    results: list[dict] = []
    folder_stack: list[str] = []

    # Tokenize: emit (type, payload) events for H3 open, DL close, A link.
    # Use finditer to walk the file in order.
    token_re = re.compile(
        r'(<H3[^>]*>.*?</H3>)'        # H3 folder open
        r'|(</DL>)'                    # DL close → pop folder
        r'|(<DT>\s*<A\s[^>]*HREF="[^"]+"[^>]*>.*?</A>)',  # bookmark
        re.IGNORECASE | re.DOTALL,
    )

    for m in token_re.finditer(content):
        if m.group(1):  # H3
            h3_match = _H3_RE.search(m.group(1))
            if h3_match:
                folder_name = _strip_tags(h3_match.group(1)).strip()
                if folder_name:
                    folder_stack.append(folder_name)
        elif m.group(2):  # </DL>
            if folder_stack:
                folder_stack.pop()
        elif m.group(3):  # <DT><A>
            a_match = _HREF_RE.search(m.group(3))
            if a_match:
                url = a_match.group(1).strip()
                title = _strip_tags(a_match.group(2)).strip() or url
                if url:
                    results.append({
                        "url": url,
                        "title": title,
                        "tags": list(folder_stack),
                    })

    return results


def _strip_tags(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r'<[^>]+>', '', text)


def _write_bookmark_md(item: KnowledgeItem, tags: list[str], content: str = "", sources: list[str] | None = None) -> Path:
    """Write a bookmark item to knowledge/items/{id}.md."""
    if sources is None:
        sources = ["bookmark"]
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
sources: {json.dumps(sources)}
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
    from backend.services.knowledge_sync import parse_frontmatter

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
            # Merge sources + tags (don't overwrite content)
            md_path = ITEMS_DIR / f"{item_id}.md"
            if md_path.exists():
                existing_fm = parse_frontmatter(md_path) or {}
                existing_sources = (
                    existing_fm.get("sources", [])
                    if isinstance(existing_fm.get("sources"), list)
                    else ["bookmark"]
                )
                existing_tags = (
                    existing_fm.get("tags", [])
                    if isinstance(existing_fm.get("tags"), list)
                    else []
                )
                merged_sources = list(dict.fromkeys(existing_sources + ["bookmark"]))
                merged_tags = list(dict.fromkeys(existing_tags + tags))

                _update_bookmark_md_frontmatter(md_path, merged_sources, merged_tags)

                existing.tags = merged_tags
                existing.updated_at = now_iso()
                knowledge_repo.upsert_item(existing)
            skipped_duplicates += 1
            continue
        
        # Optional URL validation
        is_dead = False
        if validate:
            if not validate_url(url):
                is_dead = True
                dead_links += 1
                tags = tags + ["dead_link"]
        
        # Check for similar URLs (new item)
        similar = find_similar_items(url)
        if similar:
            for sid in similar:
                tags.append(f"similar:{sid}")
            log.info("similar URLs found for %s: %s", item_id, similar)

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
        _write_bookmark_md(ki, tags, sources=["bookmark"])
        
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


def _update_bookmark_md_frontmatter(
    path: Path, sources: list[str], tags: list[str]
) -> None:
    """Update sources + tags lines in .md frontmatter, preserving body."""
    import re

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return
    parts = text.split("---", 2)
    if len(parts) < 3:
        return
    frontmatter = parts[1]
    body = parts[2]

    if re.search(r"^sources:", frontmatter, re.MULTILINE):
        frontmatter = re.sub(
            r"^sources:.*$",
            f"sources: {json.dumps(sources)}",
            frontmatter,
            flags=re.MULTILINE,
        )
    else:
        frontmatter = frontmatter.rstrip() + f"\nsources: {json.dumps(sources)}\n"

    if re.search(r"^tags:", frontmatter, re.MULTILINE):
        frontmatter = re.sub(
            r"^tags:.*$",
            f"tags: {json.dumps(tags)}",
            frontmatter,
            flags=re.MULTILINE,
        )

    path.write_text(f"---{frontmatter}---{body}", encoding="utf-8")

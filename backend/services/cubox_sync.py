"""Cubox sync service — sync cubox cards to knowledge/items/*.md.

Design notes
------------
- ``knowledge/`` lives at the project root (parent.parent.parent of this
  file: services/ → backend/ → project root).
- Falls back gracefully when ``cubox-cli`` is not installed (returns 0).
- Item IDs are derived from URL fingerprints via ``item_id_from_url``,
  so re-syncing the same card is idempotent (existing files are merged).
- Cubox folders are preserved as ``folder`` frontmatter and also injected
  into ``tags`` so they participate in domain/topic classification.
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

# Folders that carry no classification value and should not become tags.
_IGNORED_FOLDERS = {"Uncategorized", "uncategorized", "", None}


def _check_cubox_cli() -> bool:
    """Check if cubox-cli is installed."""
    try:
        result = subprocess.run(
            ["cubox-cli", "version"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _fetch_folder_nested_names() -> dict[str, str]:
    """Return a mapping of folder id → nested_name (full path).

    ``cubox-cli card list`` sometimes returns an empty ``nested_name`` even
    when the folder is nested. The ``folder list`` command reliably returns
    the full path, so we use it to backfill missing hierarchy information.
    """
    try:
        result = subprocess.run(
            ["cubox-cli", "folder", "list", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            log.warning(f"cubox-cli folder list failed: {result.stderr}")
            return {}
        folders = json.loads(result.stdout)
        if not isinstance(folders, list):
            log.warning(
                f"cubox-cli folder list returned non-list: {type(folders).__name__}"
            )
            return {}
        return {
            str(f.get("id")): f.get("nested_name", "")
            for f in folders
            if f.get("id") and f.get("nested_name")
        }
    except Exception as e:
        log.warning(f"could not fetch folder list: {e}")
        return {}


def fetch_cubox_cards(page_size: int = 100) -> list[dict]:
    """Fetch cards from cubox-cli.

    Uses ``--all`` so the full card library is returned regardless of the
    total count. ``page_size`` is passed to cubox-cli as ``--limit`` (its
    page size for pagination).

    Returns list of dicts with keys including: title, url, description,
    tags, folder, create_time, update_time.
    """
    if not _check_cubox_cli():
        log.warning("cubox-cli not installed, skipping cubox sync")
        return []

    try:
        result = subprocess.run(
            [
                "cubox-cli",
                "card",
                "list",
                "-o",
                "json",
                "--all",
                "--limit",
                str(page_size),
            ],
            capture_output=True,
            text=True,
            timeout=300,
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

        # Backfill nested folder paths so folder tags preserve hierarchy.
        nested_names = _fetch_folder_nested_names()
        if nested_names:
            for card in cards:
                folder = card.get("folder")
                if not isinstance(folder, dict):
                    continue
                folder_id = folder.get("id")
                if folder_id and not folder.get("nested_name"):
                    folder["nested_name"] = nested_names.get(str(folder_id), "")

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


def _extract_folder_tag(folder: dict | None) -> Optional[str]:
    """Return a single folder tag representing Cubox folder hierarchy."""
    if not folder or not isinstance(folder, dict):
        return None
    # Prefer nested path (e.g. "AI/大模型") because it preserves hierarchy.
    name = folder.get("nested_name") or folder.get("name") or ""
    name = name.strip()
    if name in _IGNORED_FOLDERS:
        return None
    return name


def _extract_tags(card: dict) -> list[str]:
    """Normalize Cubox tags (strings or {name: ...} objects)."""
    raw_tags = card.get("tags", [])
    if isinstance(raw_tags, list):
        tags = [
            t.get("name", "") if isinstance(t, dict) else str(t)
            for t in raw_tags
        ]
        return [t for t in tags if t]
    return []


def _card_to_item(card: dict) -> Optional[KnowledgeItem]:
    """Convert a cubox card to a KnowledgeItem."""
    url = card.get("url", "")
    if not url:
        return None
    item_id = item_id_from_url(url)
    # Prefer article_title (full title) over title (may be truncated).
    title = card.get("article_title") or card.get("title") or "Untitled"

    tags = _extract_tags(card)
    folder = card.get("folder")
    folder_tag = _extract_folder_tag(folder)
    if folder_tag and folder_tag not in tags:
        # Folder first so it has the highest classification priority.
        tags.insert(0, folder_tag)

    return KnowledgeItem(
        id=item_id,
        title=title,
        source="cubox",
        source_url=url,
        tags=tags,
        folder=folder if isinstance(folder, dict) else None,
        ingested_at=card.get("create_time", now_iso()),
        updated_at=card.get("update_time", now_iso()),
    )


def _write_item_md(item: KnowledgeItem, content: str = "", sources: list[str] | None = None) -> Path:
    """Write a knowledge item to knowledge/items/{id}.md."""
    if sources is None:
        sources = ["cubox"]
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    path = ITEMS_DIR / f"{item.id}.md"

    folder_json = json.dumps(item.folder, ensure_ascii=False) if item.folder else "null"

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
tags: {json.dumps(item.tags, ensure_ascii=False)}
concepts: []
mastery: 0
last_reviewed: null
review_count: 0
related_items: []
sources: {json.dumps(sources, ensure_ascii=False)}
folder: {folder_json}
---

# {item.title}

{content}
"""
    path.write_text(frontmatter, encoding="utf-8")
    return path


def sync_cubox_to_knowledge(page_size: int = 100, limit: int | None = None) -> int:
    """Sync cubox cards to knowledge/items/*.md.

    ``limit`` is accepted as a backwards-compatible alias for ``page_size``
    (the value is passed to cubox-cli as its pagination page size).

    Returns number of items written or merged.
    """
    from backend.repository.knowledge_repo import knowledge_repo
    from backend.services.knowledge_sync import parse_frontmatter

    page_size = limit if limit is not None else page_size
    cards = fetch_cubox_cards(page_size)
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
            # Item exists — merge sources + tags + folder (don't reset classification)
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
            existing_folder = (
                existing_fm.get("folder")
                if isinstance(existing_fm.get("folder"), dict)
                else None
            )
            merged_sources = list(dict.fromkeys(existing_sources + ["cubox"]))
            merged_tags = list(dict.fromkeys(existing_tags + item.tags))
            merged_folder = item.folder or existing_folder

            # Update .md frontmatter (sources + tags + folder) preserving body
            _update_md_frontmatter(
                md_path,
                merged_sources,
                merged_tags,
                merged_folder,
            )

            # Update SQLite tags + folder (sources not in DB schema)
            existing_item = knowledge_repo.get_item(item.id)
            if existing_item:
                existing_item.tags = merged_tags
                existing_item.folder = merged_folder
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
    path: Path,
    sources: list[str],
    tags: list[str],
    folder: dict | None,
) -> None:
    """Update sources + tags + folder lines in .md frontmatter, preserving body."""
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
            f"sources: {json.dumps(sources, ensure_ascii=False)}",
            frontmatter,
            flags=re.MULTILINE,
        )
    else:
        frontmatter = frontmatter.rstrip() + f"\nsources: {json.dumps(sources, ensure_ascii=False)}\n"

    # Replace tags line
    if re.search(r"^tags:", frontmatter, re.MULTILINE):
        frontmatter = re.sub(
            r"^tags:.*$",
            f"tags: {json.dumps(tags, ensure_ascii=False)}",
            frontmatter,
            flags=re.MULTILINE,
        )

    # Replace or add folder line
    folder_json = json.dumps(folder, ensure_ascii=False) if folder else "null"
    if re.search(r"^folder:", frontmatter, re.MULTILINE):
        frontmatter = re.sub(
            r"^folder:.*$",
            f"folder: {folder_json}",
            frontmatter,
            flags=re.MULTILINE,
        )
    else:
        frontmatter = frontmatter.rstrip() + f"\nfolder: {folder_json}\n"

    path.write_text(f"---{frontmatter}---{body}", encoding="utf-8")

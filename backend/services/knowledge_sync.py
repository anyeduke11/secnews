"""Knowledge sync service — bidirectional sync between knowledge/ .md files and SQLite.

Design notes
------------
- ``knowledge/`` lives at the project root (parent.parent.parent of this
  file: services/ → backend/ → project root).
- A minimal YAML frontmatter parser is used to avoid a ``pyyaml`` dependency.
  It handles the subset of YAML used by the ``_SCHEMA.md`` contract:
  scalar ``key: value`` pairs and ``- item`` lists. Quoted strings are
  stripped of surrounding ``"`` or ``'``.
- ``sync_item_to_db`` / ``sync_concept_to_db`` import the repository lazily
  so this module can be imported without a live DB connection (useful for
  the watchdog observer which may start before ``init_db`` runs).
- ``write_item_to_md`` preserves the markdown body below the frontmatter
  when writing back from SQLite.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger("hotspot.knowledge_sync")

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"
ITEMS_DIR = KNOWLEDGE_DIR / "items"
CONCEPTS_DIR = KNOWLEDGE_DIR / "concepts"
DRAFTS_DIR = KNOWLEDGE_DIR / "content" / "drafts"

# YAML frontmatter pattern: starts with ---, ends with ---
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _coerce_scalar(value: str):
    """Coerce a YAML scalar string to int/float when it looks numeric.

    Keeps the original string if it is not a clean number (e.g. URLs,
    dates, or identifiers that happen to start with digits).
    """
    if not value:
        return value
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def parse_frontmatter(md_path: Path) -> Optional[dict]:
    """Parse YAML frontmatter from a .md file.

    Returns dict of frontmatter fields, or None if no frontmatter found.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return None
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    # Simple YAML parsing (no pyyaml dependency)
    fm: dict = {}
    current_key: Optional[str] = None
    current_list: list = []
    for line in m.group(1).split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and not stripped.startswith("- "):
            if current_key is not None and current_list:
                fm[current_key] = current_list
                current_list = []
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value == "null":
                value = None
            elif value == "true":
                value = True
            elif value == "false":
                value = False
            elif value.startswith("[") and value.endswith("]"):
                # Inline JSON array (e.g. sources: ["cubox"], tags: ["a","b"])
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = _coerce_scalar(value)
            else:
                # Try to coerce numeric scalars so downstream isinstance
                # checks (int/float) work — e.g. mastery: 50 → int 50.
                value = _coerce_scalar(value)
            current_key = key
            if value != "":
                fm[key] = value
                current_key = None
            else:
                current_list = []
        elif stripped.startswith("- ") and current_key is not None:
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
    if current_key is not None and current_list:
        fm[current_key] = current_list
    return fm


def sync_item_to_db(md_path: Path) -> None:
    """Sync a single knowledge/items/{id}.md to SQLite."""
    fm = parse_frontmatter(md_path)
    if fm is None:
        return

    from backend.domain.knowledge_models import KnowledgeItem, now_iso
    from backend.repository.knowledge_repo import knowledge_repo

    item = KnowledgeItem(
        id=fm.get("id", md_path.stem),
        title=fm.get("title", "Untitled"),
        source=fm.get("source", "unknown"),
        source_url=fm.get("source_url"),
        domain=fm.get("domain"),
        topic=fm.get("topic"),
        type=fm.get("type"),
        difficulty=fm.get("difficulty"),
        tags=fm.get("tags", []) if isinstance(fm.get("tags"), list) else [],
        concepts=fm.get("concepts", []) if isinstance(fm.get("concepts"), list) else [],
        mastered=fm.get("mastery", 0) if isinstance(fm.get("mastery"), (int, float)) else 0,
        compiled=fm.get("compiled", False) if isinstance(fm.get("compiled"), bool) else False,
        ingested_at=fm.get("ingested_at", now_iso()),
        updated_at=now_iso(),
    )
    knowledge_repo.upsert_item(item)
    log.debug(f"synced item to db: {item.id}")


def sync_concept_to_db(md_path: Path) -> None:
    """Sync a single knowledge/concepts/{slug}.md to SQLite."""
    fm = parse_frontmatter(md_path)
    if fm is None:
        return

    from backend.domain.knowledge_models import KnowledgeConcept, now_iso
    from backend.repository.knowledge_repo import knowledge_repo

    concept = KnowledgeConcept(
        slug=fm.get("slug", md_path.stem),
        title=fm.get("title", "Untitled"),
        domain=fm.get("domain"),
        source_items=fm.get("source_items", []) if isinstance(fm.get("source_items"), list) else [],
        local_wiki_ref=fm.get("local_wiki_ref"),
        updated_at=now_iso(),
    )
    knowledge_repo.upsert_concept(concept)
    log.debug(f"synced concept to db: {concept.slug}")


def write_item_to_md(item: dict) -> None:
    """Write a knowledge item from SQLite back to knowledge/items/{id}.md."""
    item_id = item["id"]
    path = ITEMS_DIR / f"{item_id}.md"
    content = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(existing)
        if m:
            content = existing[m.end():]

    frontmatter = f"""---
id: "{item.get('id', item_id)}"
title: "{item.get('title', 'Untitled')}"
source: "{item.get('source', 'unknown')}"
source_url: "{item.get('source_url', '')}"
ingested_at: "{item.get('ingested_at', '')}"
compiled: {str(item.get('compiled', False)).lower()}
domain: {item.get('domain') or 'null'}
topic: {item.get('topic') or 'null'}
type: {item.get('type') or 'null'}
difficulty: {item.get('difficulty') or 'null'}
tags: {json.dumps(item.get('tags', []))}
concepts: {json.dumps(item.get('concepts', []))}
mastery: {item.get('mastery', 0)}
last_reviewed: {item.get('last_reviewed') or 'null'}
review_count: {item.get('review_count', 0)}
related_items: {json.dumps(item.get('related_items', []))}
---

{content}
"""
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter, encoding="utf-8")


def full_sync_items_to_db() -> int:
    """Sync all knowledge/items/*.md to SQLite. Returns count."""
    if not ITEMS_DIR.exists():
        return 0
    count = 0
    for f in ITEMS_DIR.glob("*.md"):
        sync_item_to_db(f)
        count += 1
    log.info(f"full sync: {count} items")
    return count


def full_sync_concepts_to_db() -> int:
    """Sync all knowledge/concepts/*.md to SQLite. Returns count."""
    if not CONCEPTS_DIR.exists():
        return 0
    count = 0
    for f in CONCEPTS_DIR.glob("*.md"):
        sync_concept_to_db(f)
        count += 1
    log.info(f"full sync: {count} concepts")
    return count


def sync_draft_to_db(md_path: Path) -> None:
    """Sync a single knowledge/content/drafts/*.md to SQLite.

    Drafts .md files do NOT have frontmatter — the SQLite row is the
    metadata source of truth (id/title/status/calendar_id). This function
    reconciles the filesystem with SQLite:
    - If the .md file exists but has no SQLite row, create one (title from
      the first ``# heading`` line, or the filename stem).
    - If the .md file was deleted but a SQLite row points to it, log a
      warning (the row is left untouched — deletion is handled by the
      content_service API, not by the watcher).
    """
    from backend.repository.knowledge_repo import knowledge_repo
    from backend.domain.knowledge_models import now_iso

    # file_path convention matches content_service._draft_rel_path:
    # "knowledge/content/drafts/{name}.md" (relative to project root)
    rel_path = f"knowledge/content/drafts/{md_path.name}"
    rows = knowledge_repo.list_drafts()
    match = next((r for r in rows if r["file_path"] == rel_path), None)
    if match is not None:
        # SQLite already tracks this draft — nothing to sync (drafts .md
        # has no frontmatter, so the filesystem holds only the body).
        return

    # No SQLite row — create one. Extract title from first # heading.
    title = md_path.stem  # fallback: filename
    try:
        text = md_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                break
    except Exception:
        pass

    now = now_iso()
    draft = {
        "file_path": rel_path,
        "title": title,
        "status": "draft",
        "calendar_id": None,
        "created_at": now,
        "updated_at": now,
    }
    knowledge_repo.upsert_draft(draft)
    log.info(f"synced draft from filesystem: {rel_path} (title={title!r})")


def full_sync_drafts_to_db() -> int:
    """Sync all knowledge/content/drafts/*.md to SQLite. Returns count.

    For each .md file in drafts/, ensure a SQLite row exists. Drafts .md
    files have no frontmatter — the body is the article content and the
    title is derived from the first ``# heading`` line.
    """
    if not DRAFTS_DIR.exists():
        return 0
    count = 0
    for f in DRAFTS_DIR.glob("*.md"):
        sync_draft_to_db(f)
        count += 1
    log.info(f"full sync: {count} drafts")
    return count

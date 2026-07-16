"""History import service — import archived hotspot items into knowledge base."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from backend.config import config
from backend.domain.knowledge_models import KnowledgeItem, now_iso
from backend.repository.knowledge_repo import knowledge_repo
from backend.services.data_cleaning import item_id_from_url

log = logging.getLogger("hotspot.history_import")

# hotspots.id 是 TEXT (如 "ai_量子位_0"), 所以 item_ids 用 list[str].
# 用 config.db_path 与 db.py 保持一致 (默认 backend/hotspot.db).
DB_PATH = config.db_path
ITEMS_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge" / "items"


def _fetch_hotspots(item_ids: list[str]) -> list[dict]:
    """Fetch hotspot items by ID from SQLite.

    Note: hotspots.id is TEXT, so item_ids must be strings.
    """
    if not item_ids:
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(item_ids))
    rows = conn.execute(
        f"SELECT id, title, url, summary, category FROM hotspots WHERE id IN ({placeholders})",
        item_ids,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _write_history_md(item: KnowledgeItem, summary: str = "", sources: list[str] | None = None) -> Path:
    """Write a history-imported item to knowledge/items/{id}.md."""
    if sources is None:
        sources = ["secnews_archive"]
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    path = ITEMS_DIR / f"{item.id}.md"

    frontmatter = f"""---
id: "{item.id}"
title: "{item.title}"
source: "secnews_archive"
source_url: "{item.source_url}"
ingested_at: "{item.ingested_at}"
compiled: false
domain: null
topic: null
type: null
difficulty: null
tags: []
concepts: []
mastery: 0
last_reviewed: null
review_count: 0
related_items: []
sources: {json.dumps(sources)}
---

# {item.title}

{summary}
"""
    path.write_text(frontmatter, encoding="utf-8")
    return path


def import_from_history(item_ids: list[str]) -> dict:
    """Import hotspot items into knowledge base.

    Args:
        item_ids: list of hotspot table IDs (TEXT, e.g. "ai_量子位_0")

    Returns: {imported, skipped_duplicates, errors}
    """
    if not item_ids:
        return {"imported": 0, "skipped_duplicates": 0, "errors": []}

    from backend.services.knowledge_sync import parse_frontmatter

    hotspots = _fetch_hotspots(item_ids)
    found_ids = {h["id"] for h in hotspots}
    errors = []
    for mid in item_ids:
        if mid not in found_ids:
            errors.append({"item_id": mid, "error": "not found"})

    imported = 0
    skipped_duplicates = 0

    for hs in hotspots:
        url = hs.get("url", "")
        title = hs.get("title", "Untitled")
        summary = hs.get("summary", "") or ""

        if not url:
            errors.append({"item_id": hs["id"], "error": "no url"})
            continue

        item_id = item_id_from_url(url)

        # Check if already exists
        existing = knowledge_repo.get_item(item_id)
        if existing:
            # Append secnews_archive to sources (don't overwrite content)
            md_path = ITEMS_DIR / f"{item_id}.md"
            if md_path.exists():
                existing_fm = parse_frontmatter(md_path) or {}
                existing_sources = (
                    existing_fm.get("sources", [])
                    if isinstance(existing_fm.get("sources"), list)
                    else []
                )
                if "secnews_archive" not in existing_sources:
                    merged_sources = existing_sources + ["secnews_archive"]
                    _update_history_md_sources(md_path, merged_sources)
            skipped_duplicates += 1
            continue

        now = now_iso()
        ki = KnowledgeItem(
            id=item_id,
            title=title,
            source="secnews_archive",
            source_url=url,
            ingested_at=now,
            updated_at=now,
        )

        _write_history_md(ki, summary, sources=["secnews_archive"])
        knowledge_repo.upsert_item(ki)
        imported += 1
        log.debug(f"imported from history: {item_id} ({title})")

    log.info(f"history import: {imported} new, {skipped_duplicates} dup, {len(errors)} errors")
    return {
        "imported": imported,
        "skipped_duplicates": skipped_duplicates,
        "errors": errors,
    }


def import_all_recent_history(limit: int = 100) -> dict:
    """Import all recent hotspot items into knowledge base.

    Queries the hotspots table for the most recent ``limit`` items by rowid
    DESC and imports them via :func:`import_from_history`. Used by the
    ``/api/knowledge/sync?source=all`` endpoint to sync secnews archive
    without requiring explicit item_ids.

    Returns: {imported, skipped_duplicates, errors, total_candidates}
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id FROM hotspots ORDER BY rowid DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    item_ids = [r["id"] for r in rows]
    if not item_ids:
        return {"imported": 0, "skipped_duplicates": 0, "errors": [], "total_candidates": 0}
    result = import_from_history(item_ids)
    result["total_candidates"] = len(item_ids)
    return result


def _update_history_md_sources(path: Path, sources: list[str]) -> None:
    """Update sources line in .md frontmatter, preserving everything else."""
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

    path.write_text(f"---{frontmatter}---{body}", encoding="utf-8")

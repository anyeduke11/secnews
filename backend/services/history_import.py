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


def _write_history_md(item: KnowledgeItem, summary: str = "") -> Path:
    """Write a history-imported item to knowledge/items/{id}.md."""
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

        _write_history_md(ki, summary)
        knowledge_repo.upsert_item(ki)
        imported += 1
        log.debug(f"imported from history: {item_id} ({title})")

    log.info(f"history import: {imported} new, {skipped_duplicates} dup, {len(errors)} errors")
    return {
        "imported": imported,
        "skipped_duplicates": skipped_duplicates,
        "errors": errors,
    }

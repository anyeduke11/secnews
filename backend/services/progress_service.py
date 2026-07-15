"""Progress service — mastery tracking + JSON ↔ SQLite sync.

Design: backend stores progress in SQLite (knowledge_progress table).
A mirror copy is kept at knowledge/learning/progress.json for human/Agent
inspection. The sync endpoints keep both sides consistent.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from backend.domain.knowledge_models import now_iso
from backend.repository.knowledge_repo import knowledge_repo

log = logging.getLogger("hotspot.progress")

PROGRESS_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge"
    / "learning"
    / "progress.json"
)


def list_progress(domain: Optional[str] = None) -> list[dict]:
    """List progress rows, optionally filtered by domain."""
    return knowledge_repo.list_progress(domain=domain)


def get_progress(concept_slug: str) -> Optional[dict]:
    """Get mastery progress for a single concept."""
    return knowledge_repo.get_progress(concept_slug)


def upsert_progress(
    concept_slug: str,
    mastery: int,
    tested: bool = False,
) -> dict:
    """Insert or update mastery progress.

    When tested=True, last_tested is set to now and test_count is incremented.
    When tested=False, last_tested and test_count are preserved (or initialised).
    """
    existing = knowledge_repo.get_progress(concept_slug)
    if existing:
        last_tested = now_iso() if tested else existing["last_tested"]
        test_count = existing["test_count"] + (1 if tested else 0)
    else:
        last_tested = now_iso() if tested else None
        test_count = 1 if tested else 0

    knowledge_repo.upsert_progress(
        concept_slug=concept_slug,
        mastery=mastery,
        last_tested=last_tested,
        test_count=test_count,
    )
    log.info(f"upserted progress for {concept_slug}: mastery={mastery}, tested={tested}")
    return knowledge_repo.get_progress(concept_slug)


def sync_progress_from_md() -> dict:
    """Sync progress from knowledge/learning/progress.json to SQLite.

    Creates the JSON file with {} if it doesn't exist.
    Returns: {synced: int, total: int}
    """
    if not PROGRESS_PATH.exists():
        PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROGRESS_PATH.write_text("{}", encoding="utf-8")
        log.info("created empty progress.json")
        return {"synced": 0, "total": 0}

    data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    synced = 0
    for slug, info in data.items():
        knowledge_repo.upsert_progress(
            concept_slug=slug,
            mastery=info.get("mastery", 0),
            last_tested=info.get("last_tested"),
            test_count=info.get("test_count", 0),
        )
        synced += 1
    log.info(f"synced {synced} progress entries from JSON to SQLite")
    return {"synced": synced, "total": len(data)}


def write_progress_to_md() -> dict:
    """Write progress from SQLite to knowledge/learning/progress.json.

    Returns: {written: int}
    """
    rows = knowledge_repo.list_progress()
    data = {}
    for r in rows:
        data[r["concept_slug"]] = {
            "mastery": r["mastery"],
            "last_tested": r["last_tested"],
            "test_count": r["test_count"],
        }
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info(f"wrote {len(data)} progress entries to JSON")
    return {"written": len(data)}

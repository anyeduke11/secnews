"""Content creation service — calendar + drafts + templates.

Bridges :mod:`backend.repository.knowledge_repo` (SQLite) with the
filesystem under ``knowledge/content/drafts/``. Draft bodies live in
``.md`` files (pure Markdown, no frontmatter); metadata lives in SQLite.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from backend.domain.knowledge_models import now_iso
from backend.repository.knowledge_repo import knowledge_repo

log = logging.getLogger("hotspot.content")

# Project root — resolve once at import time (matches SOUL_PATH pattern).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DRAFTS_DIR = PROJECT_ROOT / "knowledge" / "content" / "drafts"

TEMPLATES = [
    {"id": "deep-analysis", "name": "深度分析", "type": "analysis", "platform": "wechat"},
    {"id": "quick-news", "name": "快讯", "type": "news", "platform": "wechat"},
    {"id": "event-analysis", "name": "事件分析", "type": "event", "platform": "wechat"},
    {"id": "tutorial", "name": "教程", "type": "tutorial", "platform": "wechat"},
    {"id": "x-thread", "name": "X 长文", "type": "thread", "platform": "x"},
    {"id": "weibo-hot", "name": "微博热点", "type": "hot", "platform": "weibo"},
    {"id": "xhs-cards", "name": "小红书图文", "type": "cards", "platform": "xhs"},
]


# ── Helpers ────────────────────────────────────────────────────

def _slug(title: str) -> str:
    """Stable 12-char slug from title via md5 — guarantees uniqueness."""
    return hashlib.md5(title.encode("utf-8")).hexdigest()[:12]


def _draft_rel_path(slug: str) -> str:
    return f"knowledge/content/drafts/{slug}.md"


def _draft_abs_path(rel_path: str) -> Path:
    return PROJECT_ROOT / rel_path


def _parse_json_field(row: dict, field: str) -> Optional[object]:
    """Deserialize a JSON column; return None if missing/empty."""
    raw = row.get(field)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _decorate_calendar_row(row: dict) -> dict:
    """Deserialize JSON columns for API response."""
    row["source_items"] = _parse_json_field(row, "source_items") or []
    row["stats"] = _parse_json_field(row, "stats") or {}
    return row


# ── Calendar CRUD ──────────────────────────────────────────────

def list_calendar(year_month: Optional[str] = None) -> list[dict]:
    rows = knowledge_repo.list_calendar_entries(year_month)
    return [_decorate_calendar_row(r) for r in rows]


def create_calendar_entry(
    date: str,
    topic: str,
    type: Optional[str] = None,
    source_items: Optional[list[str]] = None,
    platform: Optional[str] = None,
) -> dict:
    now = now_iso()
    entry = {
        "date": date,
        "topic": topic,
        "type": type,
        "status": "planned",
        "source_items": source_items,
        "platform": platform,
        "created_at": now,
        "updated_at": now,
    }
    knowledge_repo.upsert_calendar_entry(entry)
    # Retrieve the inserted row to get its autoincrement id.
    rows = knowledge_repo.list_calendar_entries(None)
    # The just-inserted row is the most recently created one matching date+topic.
    match = next(
        (r for r in reversed(rows) if r["date"] == date and r["topic"] == topic),
        None,
    )
    if match is None:  # pragma: no cover — defensive
        return entry
    return _decorate_calendar_row(match)


def update_calendar_entry(id: int, **fields) -> dict:
    existing = knowledge_repo.get_calendar_entry(id)
    if existing is None:
        raise ValueError(f"calendar entry {id} not found")
    knowledge_repo.update_calendar_entry(id, fields)
    return _decorate_calendar_row(knowledge_repo.get_calendar_entry(id))


def delete_calendar_entry(id: int) -> dict:
    existing = knowledge_repo.get_calendar_entry(id)
    if existing is None:
        raise ValueError(f"calendar entry {id} not found")
    knowledge_repo.delete_calendar_entry(id)
    return {"deleted": id}


# ── Draft CRUD ─────────────────────────────────────────────────

def list_drafts(
    status: Optional[str] = None,
    calendar_id: Optional[int] = None,
) -> list[dict]:
    return knowledge_repo.list_drafts(status=status, calendar_id=calendar_id)


def get_draft(id: int) -> Optional[dict]:
    row = knowledge_repo.get_draft(id)
    if row is None:
        return None
    abs_path = _draft_abs_path(row["file_path"])
    if abs_path.exists():
        row["content"] = abs_path.read_text(encoding="utf-8")
    else:
        row["content"] = ""
    return row


def create_draft(
    title: str,
    content: str,
    calendar_id: Optional[int] = None,
) -> dict:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug(title)
    rel_path = _draft_rel_path(slug)
    abs_path = _draft_abs_path(rel_path)
    abs_path.write_text(content, encoding="utf-8")
    now = now_iso()
    draft = {
        "file_path": rel_path,
        "title": title,
        "status": "draft",
        "calendar_id": calendar_id,
        "created_at": now,
        "updated_at": now,
    }
    knowledge_repo.upsert_draft(draft)
    # Fetch the inserted row by file_path to retrieve its autoincrement id.
    rows = knowledge_repo.list_drafts()
    match = next((r for r in rows if r["file_path"] == rel_path), None)
    if match is None:  # pragma: no cover — defensive
        draft["id"] = None
        return draft
    return match


def update_draft(
    id: int,
    content: Optional[str] = None,
    title: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    existing = knowledge_repo.get_draft(id)
    if existing is None:
        raise ValueError(f"draft {id} not found")
    fields: dict = {}
    if title is not None:
        fields["title"] = title
    if status is not None:
        fields["status"] = status
    if fields:
        knowledge_repo.update_draft(id, fields)
    if content is not None:
        abs_path = _draft_abs_path(existing["file_path"])
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
    return knowledge_repo.get_draft(id)


def delete_draft(id: int) -> dict:
    existing = knowledge_repo.get_draft(id)
    if existing is None:
        raise ValueError(f"draft {id} not found")
    abs_path = _draft_abs_path(existing["file_path"])
    if abs_path.exists():
        abs_path.unlink()
    knowledge_repo.delete_draft(id)
    return {"deleted": id}


# ── Templates ──────────────────────────────────────────────────

def list_templates() -> list[dict]:
    return list(TEMPLATES)

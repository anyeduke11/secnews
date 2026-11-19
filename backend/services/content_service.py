"""Content creation service — calendar + drafts + templates.

Bridges :mod:`backend.repository.knowledge_repo` (SQLite) with the
filesystem under ``llm-wiki-2.0/content/drafts/``. Draft bodies live in
``.md`` files (pure Markdown, no frontmatter); metadata lives in SQLite.

v0.6.3 P3-4 收官: 路径全部从 ``backend.wiki_fs.paths`` 导入, 旧 ``knowledge/``
根已下线。``_draft_rel_path`` 返回路径改为 ``llm-wiki-2.0/...`` 相对格式,
供 SQLite 列存查 (下游读取方可同步识别)。
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from backend.domain.knowledge_models import now_iso
from backend.repository.knowledge_repo import knowledge_repo
from backend.wiki_fs.paths import (
    CALENDAR_PATH,
    DRAFTS_DIR,
    LEARNING_DONE_DIR,
    LEARNING_PENDING_DIR,
)

log = logging.getLogger("hotspot.content")

TEMPLATES = [
    {"id": "deep-analysis", "name": "深度分析", "type": "analysis", "platform": "wechat"},
    {"id": "quick-news", "name": "快讯", "type": "news", "platform": "wechat"},
    {"id": "event-analysis", "name": "事件分析", "type": "event", "platform": "wechat"},
    {"id": "tutorial", "name": "教程", "type": "tutorial", "platform": "wechat"},
    {"id": "x-thread", "name": "X 长文", "type": "thread", "platform": "x"},
    {"id": "weibo-hot", "name": "微博热点", "type": "hot", "platform": "weibo"},
    {"id": "xhs-cards", "name": "小红书图文", "type": "cards", "platform": "xhs"},
]

# Task queue directories (mirrors compiler.py LEARNING_PENDING_DIR pattern).
PENDING_DIR = LEARNING_PENDING_DIR
DONE_DIR = LEARNING_DONE_DIR


# ── Helpers ────────────────────────────────────────────────────

def _slug(title: str) -> str:
    """Stable 12-char slug from title via md5 — guarantees uniqueness."""
    return hashlib.md5(title.encode("utf-8")).hexdigest()[:12]


def _draft_rel_path(slug: str) -> str:
    return f"llm-wiki-2.0/content/drafts/{slug}.md"


def _draft_abs_path(rel_path: str) -> Path:
    """Resolve a stored rel_path like ``llm-wiki-2.0/content/drafts/<slug>.md``.

    v0.6.3 P3-4: rel_path 全部以 ``llm-wiki-2.0/`` 为前缀 (见 :func:`_draft_rel_path`)。
    实现策略: 把 ``llm-wiki-2.0/`` 前缀视为 wiki_root() 自身的占位, 替换为
    当前实际 wiki_root() 后拼接剩余部分 — 测试设 HOTSPOT_WIKI_ROOT 临时目录时,
    前缀会按字面整体被替换, 不依赖 PROJECT_ROOT 假定。
    """
    from backend.wiki_fs.paths import wiki_root
    root = wiki_root()
    parts = Path(rel_path).parts
    if parts and parts[0] == root.name:
        return root.joinpath(*parts[1:])
    # 不带前缀 (历史脏数据) — 回退到 wiki_root 直接拼, 避免 404
    return root / rel_path


def _parse_json_field(row: dict, field: str) -> object | None:
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


def _write_calendar_json() -> None:
    """Full-rewrite of knowledge/content/calendar.json from SQLite.

    Design §3.7: the calendar is persisted both in SQLite (queryable)
    and as a JSON file (human-readable, "Markdown as source of truth").
    Each mutation (create/update/delete) triggers a full rewrite so the
    file always reflects the current DB state.
    """
    rows = knowledge_repo.list_calendar_entries(None)
    dates: dict[str, list[dict]] = {}
    for r in rows:
        entry = {
            "id": r.get("id"),
            "topic": r.get("topic"),
            "type": r.get("type"),
            "status": r.get("status"),
            "source_items": _parse_json_field(r, "source_items") or [],
            "platform": r.get("platform"),
        }
        dates.setdefault(r["date"], []).append(entry)
    CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR_PATH.write_text(
        json.dumps({"dates": dates}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Calendar CRUD ──────────────────────────────────────────────

def list_calendar(year_month: str | None = None) -> list[dict]:
    rows = knowledge_repo.list_calendar_entries(year_month)
    return [_decorate_calendar_row(r) for r in rows]


def create_calendar_entry(
    date: str,
    topic: str,
    type: str | None = None,
    source_items: list[str] | None = None,
    platform: str | None = None,
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
    _write_calendar_json()
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
    _write_calendar_json()
    return _decorate_calendar_row(knowledge_repo.get_calendar_entry(id))


def delete_calendar_entry(id: int) -> dict:
    existing = knowledge_repo.get_calendar_entry(id)
    if existing is None:
        raise ValueError(f"calendar entry {id} not found")
    knowledge_repo.delete_calendar_entry(id)
    _write_calendar_json()
    return {"deleted": id}


# ── Draft CRUD ─────────────────────────────────────────────────

def list_drafts(
    status: str | None = None,
    calendar_id: int | None = None,
) -> list[dict]:
    return knowledge_repo.list_drafts(status=status, calendar_id=calendar_id)


def get_draft(id: int) -> dict | None:
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
    calendar_id: int | None = None,
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
    content: str | None = None,
    title: str | None = None,
    status: str | None = None,
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

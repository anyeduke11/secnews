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
from backend.services.knowledge_sync import KNOWLEDGE_DIR

log = logging.getLogger("hotspot.content")

# Project root — resolve once at import time (matches SOUL_PATH pattern).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DRAFTS_DIR = PROJECT_ROOT / "knowledge" / "content" / "drafts"
CALENDAR_PATH = KNOWLEDGE_DIR / "content" / "calendar.json"

TEMPLATES = [
    {"id": "deep-analysis", "name": "深度分析", "type": "analysis", "platform": "wechat"},
    {"id": "quick-news", "name": "快讯", "type": "news", "platform": "wechat"},
    {"id": "event-analysis", "name": "事件分析", "type": "event", "platform": "wechat"},
    {"id": "tutorial", "name": "教程", "type": "tutorial", "platform": "wechat"},
    {"id": "x-thread", "name": "X 长文", "type": "thread", "platform": "x"},
    {"id": "weibo-hot", "name": "微博热点", "type": "hot", "platform": "weibo"},
    {"id": "xhs-cards", "name": "小红书图文", "type": "cards", "platform": "xhs"},
]

# Task queue directories (mirrors compiler.py PENDING_DIR pattern).
PENDING_DIR = PROJECT_ROOT / "knowledge" / "learning" / "tasks" / "pending"
DONE_DIR = PROJECT_ROOT / "knowledge" / "learning" / "tasks" / "done"


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


# ── Publish ────────────────────────────────────────────────────

def create_publish_task(
    draft_id: int,
    platform: str,
    skill_name: str,
    options: Optional[dict] = None,
) -> dict:
    """Create a publish task for a draft.

    Validates draft + skill (exists, enabled, secret_id bound), then
    creates a knowledge_task row + pending task .md file, and flips the
    draft status to "publishing".
    """
    # 1. Validate draft exists (get_draft reads .md content into row["content"])
    draft = get_draft(draft_id)
    if draft is None:
        raise ValueError("draft not found")

    # 2. Validate skill exists
    skill = knowledge_repo.get_skill_by_name(skill_name)
    if skill is None:
        raise ValueError("skill not found")

    # 3. Validate skill enabled (note: _skill_row_to_dict converts to bool)
    if not skill["enabled"]:
        raise ValueError("skill disabled")

    # 4. Validate skill has secret_id bound
    if skill.get("secret_id") is None:
        raise ValueError("skill has no secret_id")

    # 5. Read draft .md content
    draft_content = draft.get("content", "")

    # 6. Create knowledge_task record
    now = now_iso()
    params = {
        "draft_id": draft_id,
        "platform": platform,
        "skill_name": skill_name,
        "options": options or {},
    }
    task = knowledge_repo.create_task("publish", params)

    # 7. Write pending task .md file (mirrors compiler.py pattern)
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    task_path = PENDING_DIR / f"task-{task.id}.md"
    options_yaml = "\n".join(
        f"  {k}: {v!r}" for k, v in (options or {}).items()
    ) or "  {}"
    task_path.write_text(
        f"""---
task_type: "publish"
status: "pending"
created_at: "{now}"
params:
  draft_id: {draft_id}
  platform: "{platform}"
  skill_name: "{skill_name}"
  options:
{options_yaml}
---

# 发布任务

## 草稿内容

{draft_content}

## 发布参数

- **平台**: {platform}
- **Skill**: {skill_name}
- **Draft ID**: {draft_id}
- **Options**: {options or {{}}}

## 执行步骤

1. 读取草稿内容（上方 Markdown 正文）
2. 调用 skill `{skill_name}` 执行发布
3. 发布成功后，将 `published_url` 写入本文件 frontmatter 的 `result.published_url`
4. 移动本文件到 `done/` 目录
5. 如失败，移动到 `failed/` 并记录 error.md
""",
        encoding="utf-8",
    )

    # 8. Update draft status to "publishing"
    knowledge_repo.update_draft(draft_id, {"status": "publishing"})

    log.info(f"created publish task {task.id} for draft {draft_id} via {skill_name}")
    return {
        "task_id": task.id,
        "status": "pending",
        "draft_id": draft_id,
        "platform": platform,
        "skill_name": skill_name,
    }


def get_publish_history(draft_id: int) -> list[dict]:
    """Return publish task history for a draft.

    For each publish task, parses params JSON to extract platform/skill_name.
    For done tasks, attempts to read the done/ task .md frontmatter for
    ``result.published_url``.
    """
    import re

    tasks = knowledge_repo.list_tasks_by_type("publish", {"draft_id": draft_id})
    history: list[dict] = []
    for t in tasks:
        # Parse params JSON (raw row stores it as a JSON string)
        params_raw = t.get("params")
        try:
            params = json.loads(params_raw) if params_raw else {}
        except (TypeError, ValueError):
            params = {}

        published_url: Optional[str] = None
        if t.get("status") == "done":
            done_path = DONE_DIR / f"task-{t['id']}.md"
            if done_path.exists():
                text = done_path.read_text(encoding="utf-8")
                if text.startswith("---"):
                    parts = text.split("---", 2)
                    frontmatter = parts[1] if len(parts) >= 3 else ""
                    # Simple line-based search for published_url
                    match = re.search(
                        r'published_url:\s*"?([^\n"]+)"?', frontmatter
                    )
                    if match:
                        published_url = match.group(1).strip()

        history.append({
            "task_id": t["id"],
            "platform": params.get("platform"),
            "skill_name": params.get("skill_name"),
            "status": t.get("status"),
            "published_url": published_url,
            "created_at": t.get("created_at"),
            "updated_at": t.get("updated_at"),
        })
    return history


def update_publish_status(
    task_id: int,
    status: str,
    published_url: Optional[str] = None,
    error: Optional[str] = None,
) -> dict:
    """Update a publish task's status and reflect it on the draft.

    - status="done" + published_url → flip draft status to "published"
    - status="failed" → roll draft status back to "draft"
    """
    task = knowledge_repo.get_task(task_id)
    if task is None:
        raise ValueError(f"task {task_id} not found")

    knowledge_repo.update_task_status(
        task_id, status, error_message=error
    )

    # Parse params to get draft_id
    params_raw = task.get("params")
    try:
        params = json.loads(params_raw) if params_raw else {}
    except (TypeError, ValueError):
        params = {}
    draft_id = params.get("draft_id")

    if draft_id is not None:
        if status == "done" and published_url:
            knowledge_repo.update_draft(draft_id, {"status": "published"})
        elif status == "failed":
            knowledge_repo.update_draft(draft_id, {"status": "draft"})

    return {"task_id": task_id, "status": status}

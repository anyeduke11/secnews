"""Skill config service — CRUD + 14 preset skills seeding.

Layered on top of ``knowledge_repo`` (skill_config CRUD). The 14 preset
skill names mirror the baoyu-* skills + knowledge-master available in the
host environment. ``seed_default_skills`` uses ``INSERT OR IGNORE`` so
re-running is safe.
"""
from __future__ import annotations

from typing import Optional

from backend.domain.knowledge_models import now_iso
from backend.repository.knowledge_repo import knowledge_repo


DEFAULT_SKILLS = [
    "baoyu-post-to-wechat",
    "baoyu-post-to-x",
    "baoyu-post-to-weibo",
    "baoyu-slide-deck",
    "baoyu-infographic",
    "baoyu-cover-image",
    "baoyu-translate",
    "baoyu-markdown-to-html",
    "baoyu-xhs-images",
    "baoyu-youtube-transcript",
    "baoyu-url-to-markdown",
    "baoyu-image-gen",
    "baoyu-compress-image",
    "knowledge-master",
]


def seed_default_skills() -> int:
    """INSERT OR IGNORE the 14 preset skills. Returns newly inserted count.

    Skips skills that already exist to avoid wasting AUTOINCREMENT ids
    (INSERT OR IGNORE with AUTOINCREMENT still bumps sqlite_sequence even
    when the row is ignored due to a UNIQUE conflict).
    """
    existing = {s["skill_name"] for s in knowledge_repo.list_skills()}
    now = now_iso()
    inserted = 0
    for name in DEFAULT_SKILLS:
        if name in existing:
            continue
        knowledge_repo.upsert_skill({
            "skill_name": name,
            "secret_id": None,
            "model_override": None,
            "prompt_template": None,
            "enabled": 1,
            "created_at": now,
            "updated_at": now,
        })
        inserted += 1
    return inserted


def list_skills(enabled: Optional[bool] = None) -> list[dict]:
    """List skill configs; auto-seeds 13 presets on first call."""
    if knowledge_repo.count_skills() == 0:
        seed_default_skills()
    return knowledge_repo.list_skills(enabled)


def get_skill(id: int) -> Optional[dict]:
    return knowledge_repo.get_skill(id)


def create_skill(
    skill_name: str,
    secret_id: Optional[int] = None,
    model_override: Optional[str] = None,
    prompt_template: Optional[str] = None,
) -> dict:
    """Create a new skill config. Returns the persisted row.

    Uses ``upsert_skill`` (INSERT OR IGNORE); if ``skill_name`` already
    exists the existing row is returned unchanged.
    """
    now = now_iso()
    knowledge_repo.upsert_skill({
        "skill_name": skill_name,
        "secret_id": secret_id,
        "model_override": model_override,
        "prompt_template": prompt_template,
        "enabled": 1,
        "created_at": now,
        "updated_at": now,
    })
    return knowledge_repo.get_skill_by_name(skill_name)


def update_skill(id: int, **fields) -> dict:
    """Update allowed fields on a skill config. Returns the updated row."""
    knowledge_repo.update_skill(id, fields)
    return knowledge_repo.get_skill(id)


def delete_skill(id: int) -> dict:
    """Delete a skill config by id."""
    knowledge_repo.delete_skill(id)
    return {"deleted": id}


def validate_skill_for_publish(skill_name: str) -> dict:
    """Validate that a skill is ready for publishing.

    Checks: skill exists, enabled, and has a secret_id bound.
    Returns ``{"valid": bool, ...}`` with a ``reason`` on failure.
    """
    skill = knowledge_repo.get_skill_by_name(skill_name)
    if skill is None:
        return {"valid": False, "reason": "skill_not_found"}
    if not skill["enabled"]:
        return {"valid": False, "reason": "skill_disabled"}
    if skill.get("secret_id") is None:
        return {"valid": False, "reason": "no_secret_bound"}
    return {"valid": True, "secret_id": skill["secret_id"]}


__all__ = [
    "DEFAULT_SKILLS",
    "seed_default_skills",
    "list_skills",
    "get_skill",
    "create_skill",
    "update_skill",
    "delete_skill",
    "validate_skill_for_publish",
]

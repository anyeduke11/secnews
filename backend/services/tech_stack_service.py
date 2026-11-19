"""v1.7 Phase 2 — TechStack 服务.

核心功能:
1. TechStack CRUD (委托 TechStackRepository)

2026-11-19: analyze_impact 文章→cg_projects 影响分析桥接随 CodeGarden 域删除退役。
"""
from __future__ import annotations

from backend.repository.tech_stack_repo import TechStackRepository


# ---------------------------------------------------------------------------
# CRUD 委托
# ---------------------------------------------------------------------------
def create_tech(id: str, name: str, category: str = "", proficiency: int = 1, notes: str = "") -> dict:
    return TechStackRepository().add(id, name, category, proficiency, notes)


def get_tech(id: str) -> dict | None:
    return TechStackRepository().get(id)


def list_tech(category: str | None = None) -> list[dict]:
    return TechStackRepository().list(category)


def update_tech(
    id: str,
    name: str | None = None,
    category: str | None = None,
    proficiency: int | None = None,
    notes: str | None = None,
) -> dict | None:
    return TechStackRepository().update(id, name, category, proficiency, notes)


def delete_tech(id: str) -> int:
    return TechStackRepository().delete(id)


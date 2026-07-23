"""v1.7 Phase 2 — TechStack 服务 + 文章→项目影响桥接.

核心功能:
1. TechStack CRUD (委托 TechStackRepository)
2. analyze_impact(article_id): 文章标签 → 匹配使用该技术栈的 cg_projects

桥接逻辑 (验收 4: FastAPI 漏洞文章匹配到使用 FastAPI 的项目):
- 从 hotspots 表读取文章 (title + summary + category)
- 用 extract_tags 提取标签 (返回 [{tag_id, confidence}])
- tag_id (如 "fastapi") 作为技术栈名称, 匹配 cg_projects.tech_stack (JSON 数组)
- 返回去重后的项目列表

设计决策:
- 匹配 cg_projects.tech_stack (技术栈名称数组, 由 codegarden_repo 维护),
  而非 tech_stack_ids (tech_stack 表 ID 数组, 目前无代码填充).
  这直接满足验收 4, 且向前兼容 (tech_stack_ids 后续填充时可扩展).
"""
from __future__ import annotations

from typing import Optional

from backend.repository.codegarden_repo import _row_to_project
from backend.repository.db import get_connection
from backend.repository.tech_stack_repo import TechStackRepository


# ---------------------------------------------------------------------------
# CRUD 委托
# ---------------------------------------------------------------------------
def create_tech(id: str, name: str, category: str = "", proficiency: int = 1, notes: str = "") -> dict:
    return TechStackRepository().add(id, name, category, proficiency, notes)


def get_tech(id: str) -> Optional[dict]:
    return TechStackRepository().get(id)


def list_tech(category: Optional[str] = None) -> list[dict]:
    return TechStackRepository().list(category)


def update_tech(
    id: str,
    name: Optional[str] = None,
    category: Optional[str] = None,
    proficiency: Optional[int] = None,
    notes: Optional[str] = None,
) -> Optional[dict]:
    return TechStackRepository().update(id, name, category, proficiency, notes)


def delete_tech(id: str) -> int:
    return TechStackRepository().delete(id)


# ---------------------------------------------------------------------------
# 影响分析桥接
# ---------------------------------------------------------------------------
def analyze_impact(article_id: str) -> dict:
    """文章 → 受影响的 CodeGarden 项目.

    Args:
        article_id: hotspots.id

    Returns:
        {
            "article_id": "...",
            "tags": [{"tag_id": "fastapi", "confidence": 0.8}, ...],
            "projects": [{...cg_project...}, ...],
            "matched_tech": ["fastapi", ...],
        }
    """
    from backend.services.extract_service import extract_tags
    from backend.repository.hotspot_repo import HotspotRepository

    hotspot = HotspotRepository().get_by_id(article_id)
    if not hotspot:
        return {"article_id": article_id, "tags": [], "projects": [], "matched_tech": []}

    # 提取标签 (title + summary + category)
    title = hotspot.title or ""
    summary = hotspot.summary or ""
    category = hotspot.category.value if hasattr(hotspot.category, "value") else str(hotspot.category)
    tags = extract_tags(summary, title, category)

    # tag_id 作为技术栈名称, 匹配 cg_projects.tech_stack (JSON 数组)
    tech_names = [t["tag_id"] for t in tags]
    projects = _find_projects_by_tech_names(tech_names)

    return {
        "article_id": article_id,
        "tags": tags,
        "matched_tech": tech_names,
        "projects": projects,
    }


def _find_projects_by_tech_names(tech_names: list[str]) -> list[dict]:
    """按技术栈名称列表查找 cg_projects (tech_stack JSON 数组包含任一名称).

    使用 json_extract + LIKE 匹配, 去重 (一个项目可能匹配多个 tech).
    跳过已归档项目 (lifecycle_stage IN ('archived', 'deprecated')).
    """
    if not tech_names:
        return []
    conn = get_connection()
    seen: set[str] = set()
    projects: list[dict] = []
    for name in tech_names:
        # tech_stack 是 JSON 数组 (如 ["fastapi", "react"]); LIKE '%\"name\"%' 精确匹配元素
        rows = conn.execute(
            """
            SELECT * FROM cg_projects
             WHERE json_extract(tech_stack, '$') LIKE ?
               AND lifecycle_stage NOT IN ('archived', 'deprecated')
            """,
            (f'%"{name}"%',),
        ).fetchall()
        for row in rows:
            pid = str(row["id"])
            if pid in seen:
                continue
            seen.add(pid)
            projects.append(_row_to_project(row))
    return projects

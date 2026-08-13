"""Phase 14 Tech Stack Drift 评估服务 — Knowledge → Codegarden 技术栈漂移检测.

职责
----
- assess_drift(): 扫描 knowledge_items 的 item_entities(entity_type='tool'),
  对比 cg_projects.tech_stack (JSON 数组), 发现新 tech 时写入 cg_drift_assessments
- get_assessments(): 查询评估列表
- update_assessment_status(): 更新评估状态

设计
----
- 不自动修改 cg_projects.tech_stack, 仅记录评估结果到 cg_drift_assessments
- 已匹配的 tech 不重复评估
- 新 tech 但无项目使用 → 跳过 (不生成评估记录)
"""
from __future__ import annotations

from typing import Optional

from backend.logging_config import logger
from backend.repository.db import get_connection


# 有效 status 枚举
VALID_DRIFT_STATUSES = ("pending", "reviewed", "applied", "dismissed")


def assess_drift(limit: int = 500) -> dict:
    """执行 tech_stack drift 评估.

    流程:
      1. 扫描 knowledge_items 表, JOIN item_entities WHERE entity_type='tool'
      2. 按 entity_name 分组, 统计每个 tech 出现在多少个 knowledge items 中
      3. 对每个 tech 查询 cg_projects WHERE tech_stack JSON 包含该名称
      4. 若 tech 在某个项目的 tech_stack 中 → 检查是否已有评估记录, 无则插入
      5. 返回报告: {new_techs, affected_projects, matched_count}

    Returns:
        {
            "new_techs": [{"tech_name": "...", "count": N, "projects": [...]}],
            "affected_projects": [{"project_id": "...", "project_name": "...", "techs": [...]}],
            "matched_count": N,
            "skipped_no_project": [tech_name],  # 有 tech 但无项目使用
        }
    """
    conn = get_connection()
    new_techs: list[dict] = []
    affected_projects_map: dict[str, dict] = {}
    matched_count = 0
    skipped_no_project: list[str] = []

    # 1. 按 entity_name 分组统计
    rows = conn.execute(
        """
        SELECT ie.entity_name, ie.item_id AS source_item_id, ki.domain
        FROM item_entities ie
        JOIN knowledge_items ki ON ki.id = ie.item_id
        WHERE ie.entity_type = 'tool'
        ORDER BY ie.entity_name
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()

    # 按 tech_name 分组
    tech_groups: dict[str, dict] = {}
    for r in rows:
        name = str(r["entity_name"])
        if name not in tech_groups:
            tech_groups[name] = {
                "tech_name": name,
                "count": 0,
                "source_item_ids": [],
                "domains": set(),
            }
        tech_groups[name]["count"] += 1
        tech_groups[name]["source_item_ids"].append(str(r["source_item_id"]))
        if r["domain"]:
            tech_groups[name]["domains"].add(str(r["domain"]))

    # 2. 对每个 tech 查询 cg_projects
    for tech_name, group in tech_groups.items():
        # 查找 tech_stack JSON 包含该 tech 的项目
        project_rows = conn.execute(
            """
            SELECT id, name, display_name
            FROM cg_projects
            WHERE json_extract(tech_stack, '$') LIKE ?
              AND lifecycle_stage NOT IN ('archived', 'deprecated')
            """,
            (f'%"{tech_name}"%',),
        ).fetchall()

        if not project_rows:
            skipped_no_project.append(tech_name)
            continue

        projects = []
        for pr in project_rows:
            pid = str(pr["id"])
            pname = str(pr["display_name"] or pr["name"])

            # 3. 检查是否已有评估记录
            existing = conn.execute(
                "SELECT id FROM cg_drift_assessments WHERE project_id = ? AND tech_name = ?",
                (pid, tech_name),
            ).fetchone()

            if existing is None:
                # 插入新评估记录
                source_item_id = group["source_item_ids"][0] if group["source_item_ids"] else None
                source_domain = next(iter(group["domains"])) if group["domains"] else None
                conn.execute(
                    """
                    INSERT OR IGNORE INTO cg_drift_assessments
                        (project_id, tech_name, source_item_id, source_domain)
                    VALUES (?, ?, ?, ?)
                    """,
                    (pid, tech_name, source_item_id, source_domain),
                )
                matched_count += 1

            projects.append({"project_id": pid, "project_name": pname})

            # 记录到 affected_projects_map
            if pid not in affected_projects_map:
                affected_projects_map[pid] = {
                    "project_id": pid,
                    "project_name": pname,
                    "techs": [],
                }
            if tech_name not in affected_projects_map[pid]["techs"]:
                affected_projects_map[pid]["techs"].append(tech_name)

        new_techs.append({
            "tech_name": tech_name,
            "count": group["count"],
            "projects": projects,
        })

    report = {
        "new_techs": new_techs,
        "affected_projects": list(affected_projects_map.values()),
        "matched_count": matched_count,
        "skipped_no_project": skipped_no_project,
    }

    logger.info(
        f"drift assessment: {len(new_techs)} techs assessed, "
        f"{matched_count} new assessments, "
        f"{len(affected_projects_map)} affected projects, "
        f"{len(skipped_no_project)} skipped (no project)"
    )
    return report


def get_assessments(
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """查询 drift 评估列表.

    Args:
        status: 筛选状态 (pending/reviewed/applied/dismissed)
        project_id: 筛选项目 ID
        limit: 分页大小 (默认 100)
        offset: 偏移量

    Returns:
        {"items": [...], "total": N, "limit": N, "offset": N}
    """
    conn = get_connection()
    where_clauses: list[str] = []
    params: list = []

    if status:
        where_clauses.append("d.status = ?")
        params.append(status)
    if project_id:
        where_clauses.append("d.project_id = ?")
        params.append(project_id)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # 总数
    total_row = conn.execute(
        f"SELECT COUNT(*) FROM cg_drift_assessments d WHERE {where_sql}",
        params,
    ).fetchone()
    total = total_row[0] if total_row else 0

    # 列表 (JOIN cg_projects 获取项目名称)
    rows = conn.execute(
        f"""
        SELECT d.*, p.display_name AS project_name, p.name AS project_slug
        FROM cg_drift_assessments d
        LEFT JOIN cg_projects p ON p.id = d.project_id
        WHERE {where_sql}
        ORDER BY d.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (*params, int(limit), int(offset)),
    ).fetchall()

    items = [dict(r) for r in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def update_assessment_status(
    assessment_id: int,
    status: str,
    notes: Optional[str] = None,
) -> Optional[dict]:
    """更新评估状态.

    Args:
        assessment_id: 评估记录 ID
        status: 新状态 (reviewed/applied/dismissed)
        notes: 备注 (可选)

    Returns:
        更新后的评估记录, 或 None (记录不存在)
    """
    if status not in VALID_DRIFT_STATUSES:
        raise ValueError(f"无效状态: {status!r}, 有效值: {VALID_DRIFT_STATUSES}")

    conn = get_connection()
    if status in ("reviewed", "applied", "dismissed"):
        if notes:
            conn.execute(
                """
                UPDATE cg_drift_assessments
                SET status = ?, reviewed_at = datetime('now'), notes = ?
                WHERE id = ?
                """,
                (status, notes, assessment_id),
            )
        else:
            conn.execute(
                """
                UPDATE cg_drift_assessments
                SET status = ?, reviewed_at = datetime('now')
                WHERE id = ?
                """,
                (status, assessment_id),
            )
    else:
        if notes:
            conn.execute(
                "UPDATE cg_drift_assessments SET status = ?, notes = ? WHERE id = ?",
                (status, notes, assessment_id),
            )
        else:
            conn.execute(
                "UPDATE cg_drift_assessments SET status = ? WHERE id = ?",
                (status, assessment_id),
            )

    # 返回更新后的记录
    row = conn.execute(
        "SELECT * FROM cg_drift_assessments WHERE id = ?",
        (assessment_id,),
    ).fetchone()
    return dict(row) if row else None


__all__ = [
    "assess_drift",
    "get_assessments",
    "update_assessment_status",
    "VALID_DRIFT_STATUSES",
]
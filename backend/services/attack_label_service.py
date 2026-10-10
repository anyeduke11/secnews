"""MP-2 AttackLabelService — 多语义入口 (技战法标签统一查询).

职责
----
- ``get_event_techniques_for_type(event_type_id)``: 返回某事件类型的已审定技战法链
  (按 stage 时间线排序, MP-2 核心渲染入口 — EventTypeCard 消费)
- ``get_knowledge_for_techniques(technique_ids)``: MP-4 知识↔判断层双向关联预留 stub
  (knowledge_technique_ref 表属 MP-4 范围, 本期不建)

设计
----
- 只读已审定 ``event_technique_map`` (不读 pending candidates — 候选未经人审不可外显)
- 每条 map 行回填 technique name (从 attack_techniques JOIN)
- MP-4 接入点: ``get_knowledge_for_techniques`` 留 TODO, 签名冻结, 返回空列表
"""
from __future__ import annotations

from backend.repository.db import get_connection
from backend.repository.event_technique_repo import EventTypeRepo


class AttackLabelService:
    """技战法标签多语义入口 (MP-2 L2 事件类型 / MP-4 L3 响应知识复用)."""

    def __init__(self) -> None:
        self.event_type_repo = EventTypeRepo()

    # ------------------------------------------------------------------
    # L2: 事件类型 → 技战法链 (MP-2 核心入口)
    # ------------------------------------------------------------------
    def get_event_techniques_for_type(self, event_type_id: str) -> dict:
        """返回某事件类型的已审定技战法链.

        Returns:
            {
              "event_type": {id, name_zh, name_en, description, kill_chain_stages},
              "techniques": [
                {map_id, technique_id, technique_name, stage, note,
                 approved_at, approved_by, source_url}  # source_url 为追溯链终点
              ],
              "stage_order": [kill_chain_stages 顺序]
            }
        """
        et = self.event_type_repo.get(event_type_id)
        if not et:
            return {"event_type": None, "techniques": [], "stage_order": []}

        conn = get_connection()
        rows = conn.execute(
            """
            SELECT m.id AS map_id, m.technique_id, m.stage, m.note,
                   m.candidate_id, m.source_report_id, m.approved_at, m.approved_by,
                   t.name AS technique_name,
                   r.source_url
            FROM event_technique_map m
            LEFT JOIN attack_techniques t ON t.id = m.technique_id
            LEFT JOIN incident_reports r ON r.id = m.source_report_id
            WHERE m.event_type_id = ?
            ORDER BY m.stage ASC, m.technique_id ASC
            """,
            (event_type_id,),
        ).fetchall()

        techniques = []
        for r in rows:
            d = dict(r)
            d["technique_name"] = d.get("technique_name") or d["technique_id"]
            techniques.append(d)

        return {
            "event_type": {
                "id": et["id"],
                "name_zh": et["name_zh"],
                "name_en": et["name_en"],
                "description": et["description"],
                "kill_chain_stages": et["kill_chain_stages"],
            },
            "techniques": techniques,
            "stage_order": et["kill_chain_stages"],
        }

    # ------------------------------------------------------------------
    # MP-4 预留 stub (签名冻结, 本期返回空)
    # ------------------------------------------------------------------
    def get_knowledge_for_techniques(self, technique_ids: list[str]) -> list[dict]:
        """知识↔判断层双向关联查询 (MP-4 实现).

        TODO(MP-4): knowledge_technique_ref 表建好后:
            SELECT k.* FROM v1_knowledge k
            JOIN knowledge_technique_ref ref ON ref.knowledge_id = k.id
            WHERE ref.technique_id IN (?) AND k.status = 'published'
        本期 (MP-2) 表未建, 返回空列表 — 调用方 (MP-4 JudgmentContextBuilder)
        按空 section 处理即可, 签名不变.
        """
        return []


__all__ = ["AttackLabelService"]

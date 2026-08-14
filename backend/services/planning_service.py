"""PlanningService — Phase 13 知识规划动作生成与管理.

根据知识条目的生命周期阶段 (kl:*) 自动生成规划动作
(read / link / refine / publish / review), 支持状态更新与查询。
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection


class PlanningService:
    """知识规划动作服务.

    扫描 knowledge_items 表, 按生命周期阶段规则生成 planning_actions 记录,
    并管理其状态流转。
    """

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # generate_actions
    # ------------------------------------------------------------------
    def generate_actions(self) -> dict[str, int]:
        """扫描 knowledge_items 并为符合规则的生命周期阶段生成规划动作.

        Rules:
          - kl:raw     → read     (priority=8, 无阅读记录)
          - kl:refine  → link     (priority=7, 关联数 < 3)
          - kl:link    → refine   (priority=6, 评分 < 8.0)
          - kl:structure → publish (priority=5, 已稳定 24h)
          - kl:publish → review   (priority=4, 已发布 7 天)

        Returns:
            dict: {action_type: count, ...} 按动作类型统计的生成数量。
        """
        conn = get_connection()
        counts: dict[str, int] = {"read": 0, "link": 0, "refine": 0, "publish": 0, "review": 0}

        # ── Rule 1: kl:raw → read ──────────────────────────────────
        rows = conn.execute(
            """
            SELECT ki.id, ki.title
            FROM knowledge_items ki
            WHERE ki.lifecycle = 'kl:raw'
              AND NOT EXISTS (
                  SELECT 1 FROM reading_states rs
                  WHERE rs.entity_type = 'knowledge_item'
                    AND rs.entity_id = ki.id
              )
            """
        ).fetchall()
        for row in rows:
            self._insert_action(
                conn,
                item_id=row["id"],
                action_type="read",
                priority=8,
                title=f"阅读: {row['title']}",
                current_stage="kl:raw",
                target_stage="kl:refine",
            )
            counts["read"] += 1

        # ── Rule 2: kl:refine → link (关联数 < 3) ──────────────────
        rows = conn.execute(
            """
            SELECT ki.id, ki.title,
                   (SELECT COUNT(*) FROM knowledge_links kl
                    WHERE kl.from_item_id = ki.id OR kl.to_item_id = ki.id) AS link_cnt
            FROM knowledge_items ki
            WHERE ki.lifecycle = 'kl:refine'
            """
        ).fetchall()
        for row in rows:
            if row["link_cnt"] >= 3:
                continue
            self._insert_action(
                conn,
                item_id=row["id"],
                action_type="link",
                priority=7,
                title=f"关联: {row['title']} (关联数不足)",
                current_stage="kl:refine",
                target_stage="kl:link",
            )
            counts["link"] += 1

        # ── Rule 3: kl:link → refine (评分 < 8.0) ──────────────────
        rows = conn.execute(
            """
            SELECT ki.id, ki.title,
                   COALESCE((SELECT MAX(a.score) FROM ai_scores a
                             WHERE a.hotspot_id = ki.id), 0) AS score
            FROM knowledge_items ki
            WHERE ki.lifecycle = 'kl:link'
            """
        ).fetchall()
        for row in rows:
            score = row["score"]
            if score >= 8.0:
                continue
            self._insert_action(
                conn,
                item_id=row["id"],
                action_type="refine",
                priority=6,
                title=f"精炼: {row['title']} (评分{score})",
                current_stage="kl:link",
                target_stage="kl:structure",
            )
            counts["refine"] += 1

        # ── Rule 4: kl:structure → publish (已稳定 24h) ────────────
        rows = conn.execute(
            """
            SELECT ki.id, ki.title
            FROM knowledge_items ki
            WHERE ki.lifecycle = 'kl:structure'
              AND ki.updated_at <= datetime('now', '-1 day')
            """
        ).fetchall()
        for row in rows:
            self._insert_action(
                conn,
                item_id=row["id"],
                action_type="publish",
                priority=5,
                title=f"发布: {row['title']} (已稳定)",
                current_stage="kl:structure",
                target_stage="kl:publish",
            )
            counts["publish"] += 1

        # ── Rule 5: kl:publish → review (已发布 7 天) ──────────────
        rows = conn.execute(
            """
            SELECT ki.id, ki.title
            FROM knowledge_items ki
            WHERE ki.lifecycle = 'kl:publish'
              AND ki.updated_at <= datetime('now', '-7 days')
            """
        ).fetchall()
        for row in rows:
            self._insert_action(
                conn,
                item_id=row["id"],
                action_type="review",
                priority=4,
                title=f"复习: {row['title']} (已发布7天)",
                current_stage="kl:publish",
                target_stage="kl:refine",
            )
            counts["review"] += 1

        total = sum(counts.values())
        logger.info(
            "planning actions generated",
            extra={"trace_id": "", "counts": str(counts), "total": total},
        )
        return counts

    # ------------------------------------------------------------------
    # update_action_status
    # ------------------------------------------------------------------
    def update_action_status(self, action_id: int, status: str) -> bool:
        """更新指定规划动作的状态并记录操作日志.

        Args:
            action_id: planning_actions.id
            status: 目标状态 ('in_progress', 'completed', 'dismissed')

        Returns:
            True 如果更新成功, False 如果记录不存在或状态不合法。
        """
        conn = get_connection()

        # 读取当前动作
        row = conn.execute(
            "SELECT id, action_type, item_id, status FROM planning_actions WHERE id = ?",
            (action_id,),
        ).fetchone()
        if row is None:
            logger.warning(
                "planning action not found",
                extra={"trace_id": "", "action_id": action_id},
            )
            return False

        current_status = row["status"]
        if current_status == "pending" and status == "in_progress":
            conn.execute(
                "UPDATE planning_actions SET status = ? WHERE id = ?",
                (status, action_id),
            )
            self._log_event(conn, action_id, row["action_type"], row["item_id"], "started")
            logger.info(
                "planning action started",
                extra={"trace_id": "", "action_id": action_id, "action_type": row["action_type"]},
            )
            return True

        if current_status == "in_progress" and status in ("completed", "dismissed"):
            if status == "completed":
                conn.execute(
                    "UPDATE planning_actions SET status = ?, completed_at = datetime('now') WHERE id = ?",
                    (status, action_id),
                )
            else:
                conn.execute(
                    "UPDATE planning_actions SET status = ?, dismissed_at = datetime('now') WHERE id = ?",
                    (status, action_id),
                )
            self._log_event(conn, action_id, row["action_type"], row["item_id"], status)
            logger.info(
                "planning action updated",
                extra={"trace_id": "", "action_id": action_id, "status": status},
            )
            return True

        logger.warning(
            "invalid status transition for planning action",
            extra={
                "trace_id": "",
                "action_id": action_id,
                "current_status": current_status,
                "requested_status": status,
            },
        )
        return False

    # ------------------------------------------------------------------
    # get_actions
    # ------------------------------------------------------------------
    def get_actions(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """查询规划动作列表.

        Args:
            status: 可选的状态过滤 ('pending', 'in_progress', 'completed', 'dismissed')
            limit: 返回条数上限 (默认 50)

        Returns:
            dict 列表, 每个 dict 包含 planning_actions 表的所有字段。
        """
        conn = get_connection()
        if status:
            rows = conn.execute(
                "SELECT * FROM planning_actions WHERE status = ? ORDER BY priority DESC, created_at ASC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM planning_actions ORDER BY priority DESC, created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _insert_action(
        self,
        conn,
        item_id: str,
        action_type: str,
        priority: int,
        title: str,
        current_stage: str,
        target_stage: str,
    ) -> None:
        """插入一条 planning_action (若已存在同 item_id + action_type 的 pending 记录则跳过)."""
        existing = conn.execute(
            "SELECT id FROM planning_actions WHERE item_id = ? AND action_type = ? AND status = 'pending'",
            (item_id, action_type),
        ).fetchone()
        if existing is not None:
            return  # 去重

        conn.execute(
            """INSERT INTO planning_actions
               (item_id, action_type, priority, title, current_stage, target_stage, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (item_id, action_type, priority, title, current_stage, target_stage),
        )
        action_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self._log_event(conn, action_id, action_type, item_id, "created")

    @staticmethod
    def _log_event(
        conn,
        action_id: int,
        action_type: str,
        item_id: str,
        event: str,
    ) -> None:
        """向 planning_action_log 表写入一条事件记录."""
        conn.execute(
            """INSERT INTO planning_action_log
               (action_id, action_type, item_id, event)
               VALUES (?, ?, ?, ?)""",
            (action_id, action_type, item_id, event),
        )


__all__ = ["PlanningService"]
"""v1.0 T15 SignalService — 列表 + 聚合 (复用 T05 v1_signals + v1_subjects + v1_materials).

T15 §通过证据第 1 点 "情报 (Intel) 入口真实化": list_recent_signals(days, case_id?) 走 v1_signals
近 N 天窗口, JOIN v1_subjects (subject 实体) + v1_materials (物料实体, 走 evidence_refs).

注意: 与 SK-01 sk01_daily_priority._query_signals_recent 区分: 本模块返列表
(每行 subject_id+material_id+summary+confidence+occurred_at), SK-01 返 top_items
(经 dsh mock 摘要 + 受关注 subject 变化).
"""
from __future__ import annotations

import sqlite3
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection


def list_recent_signals(
    days: int = 7, *, case_id: str | None = None, limit: int = 50,
    subject_id: str | None = None,
) -> list[dict[str, Any]]:
    """列 v1_signals 近 N 天 + 关联 subject/material.

    Parameters
    ----------
    days:
        时间窗口, 默认 7 天 (T15 情报入口同 SK-01 7 天).
    case_id:
        可选 — 若提供, 走 v1_materials → v1_case_materials → v1_subjects 关联过滤
        (与 signal.subject_id 匹配). 用于 Case 维度下钻.
    limit:
        返回条数, 默认 50 (前 50 条按 occurred_at DESC).
    subject_id:
        v0.8.5 D1.3 — 可选, 按 subject 过滤 (Subject 抽屉下钻).
    """
    conn = get_connection()
    try:
        if subject_id:
            rows = conn.execute(
                "SELECT s.id, s.subject_id, s.material_id, s.summary, s.occurred_at, "
                "       s.confidence, s.status, sub.canonical_name AS subject_name "
                "FROM v1_signals s "
                "LEFT JOIN v1_subjects sub ON s.subject_id = sub.id "
                "WHERE s.occurred_at >= datetime('now', ?) "
                "AND s.subject_id = ? "
                "ORDER BY s.occurred_at DESC LIMIT ?",
                (f"-{days} days", subject_id, limit),
            ).fetchall()
        elif case_id:
            # case_id 过滤: 走 v1_actions → judgment_id → case_id 关联 (T08 case_action)
            # 当前 v1_actions 表无 case_id 字段 (T12+ 才加), 暂走 material_id 反查
            rows = conn.execute(
                "SELECT s.id, s.subject_id, s.material_id, s.summary, s.occurred_at, "
                "       s.confidence, s.status, sub.canonical_name AS subject_name "
                "FROM v1_signals s "
                "LEFT JOIN v1_subjects sub ON s.subject_id = sub.id "
                "WHERE s.occurred_at >= datetime('now', ?) "
                "AND s.material_id IN ( "
                "  SELECT DISTINCT material_id FROM v1_case_materials WHERE case_id = ? "
                ") "
                "ORDER BY s.occurred_at DESC LIMIT ?",
                (f"-{days} days", case_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT s.id, s.subject_id, s.material_id, s.summary, s.occurred_at, "
                "       s.confidence, s.status, sub.canonical_name AS subject_name "
                "FROM v1_signals s "
                "LEFT JOIN v1_subjects sub ON s.subject_id = sub.id "
                "WHERE s.occurred_at >= datetime('now', ?) "
                "ORDER BY s.occurred_at DESC LIMIT ?",
                (f"-{days} days", limit),
            ).fetchall()
    except sqlite3.OperationalError as e:
        # migration 096 未跑 (T15 演练 dry-run 模式)
        return []
    items = [
        {
            "id": r[0], "subject_id": r[1], "material_id": r[2],
            "summary": r[3], "occurred_at": r[4], "confidence": r[5],
            "status": r[6], "subject_name": r[7],
        }
        for r in rows
    ]
    # T17 SSE 5 事件源: list 走完推 v1_signal 事件 (fire-and-forget, 仅 1 条; T19 全量收口前容忍失败)
    if items:
        try:
            from backend.observability import get_trace_id
            from backend.repository.outbox_repo import OutboxRepo
            OutboxRepo().enqueue(
                event_type="v1_signal",
                aggregate_type="signal",
                aggregate_id="list",  # signal 列表本身作为聚合
                revision=0,
                payload={
                    "count": len(items), "sample_id": items[0]["id"],
                },
                trace_id=get_trace_id() or "no-trace",
            )
        except Exception as e:
            logger.debug(f"v1_signal outbox enqueue skipped: {e}")
    return items

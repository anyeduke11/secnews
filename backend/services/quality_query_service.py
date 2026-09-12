"""quality_query_service — quality 域只读查询服务 (Batch 2 SQL 下沉).

把 /api/quality 路由内 3 处直连 SQL 收敛到服务层:
- source_reputation 全表 (按 score 倒序) — 表已有 SourceReputationRepository,
  但"全表列表"语义此前只存在于路由层, 先落服务; Batch 3 可再并入 repo.
- quality_rejection_log 分页查询 / 按 gate 聚合统计 — 表无 repo, 先落服务.

依赖方向: 仅 import backend.repository.db, 不触碰 backend.api.
"""
from __future__ import annotations

from typing import Any

from backend.repository.db import get_connection


def list_source_reputation() -> list[dict[str, Any]]:
    """全量 source 信誉行, 按 score 倒序. blacklist 转 bool."""
    rows = get_connection().execute(
        "SELECT source, score, blacklist, pass_count, fail_count, last_updated "
        "FROM source_reputation ORDER BY score DESC"
    ).fetchall()
    return [
        {
            "source": r["source"],
            "score": r["score"],
            "blacklist": bool(r["blacklist"]),
            "pass_count": r["pass_count"],
            "fail_count": r["fail_count"],
            "last_updated": r["last_updated"],
        }
        for r in rows
    ]


def query_rejection_log(
    gate_name: str | None = None,
    source_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """分页查询 quality_rejection_log. 返回 {items,total,page,page_size}."""
    conn = get_connection()
    where_clauses: list[str] = ["1=1"]
    params: list = []

    if gate_name:
        where_clauses.append("rejected_by = ?")
        params.append(gate_name)
    if source_id:
        where_clauses.append("source_id LIKE ?")
        params.append(f"%{source_id}%")
    if date_from:
        where_clauses.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("created_at <= ?")
        params.append(date_to)

    where = " AND ".join(where_clauses)
    offset = (page - 1) * page_size

    count_row = conn.execute(
        f"SELECT COUNT(*) as cnt FROM quality_rejection_log WHERE {where}",
        params,
    ).fetchone()
    total = count_row["cnt"] if count_row else 0

    rows = conn.execute(
        f"SELECT * FROM quality_rejection_log WHERE {where} "
        "ORDER BY created_at DESC LIMIT ? OFFSET ?",
        [*params, page_size, offset],
    ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def rejection_stats(
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """按 gate 聚合 + 按日趋势统计拒绝次数. 返回 {by_gate, trend}."""
    conn = get_connection()
    where_clauses: list[str] = ["1=1"]
    params: list = []

    if date_from:
        where_clauses.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("created_at <= ?")
        params.append(date_to)

    where = " AND ".join(where_clauses)

    rows = conn.execute(
        f"""SELECT rejected_by as gate_name, COUNT(*) as count
            FROM quality_rejection_log
            WHERE {where}
            GROUP BY rejected_by
            ORDER BY count DESC""",
        params,
    ).fetchall()

    trend_rows = conn.execute(
        f"""SELECT DATE(created_at) as day, COUNT(*) as count
            FROM quality_rejection_log
            WHERE {where}
            GROUP BY DATE(created_at)
            ORDER BY day ASC""",
        params,
    ).fetchall()

    return {
        "by_gate": [dict(r) for r in rows],
        "trend": [dict(r) for r in trend_rows],
    }

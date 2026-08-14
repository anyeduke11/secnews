"""v1.7 Phase 17 — 注意力评分服务 (Attention Scorer).

5 维加权评分系统:

| 维度 | 权重 | 来源 |
|------|------|------|
| view_count | 0.25 | COUNT of attention_events WHERE event_type='view' |
| dwell_time | 0.25 | SUM of detail_json.dwell_seconds (event_type='dwell') |
| scroll_depth | 0.15 | MAX of detail_json.depth_pct (event_type='scroll') |
| is_favorited | 0.20 | 1.0 若该条目的 url 在 favorites 表中, 否则 0.0 |
| annotation_count | 0.15 | COUNT of annotations WHERE entity_id=item_id |

公式:
    score = min(100, round(sum(dimension_normalized * weight) * 100))

每个维度先归一化到 [0, 1]:
    - view_count: min(count / 20, 1.0)       (20 次浏览 = 满分)
    - dwell_time: min(seconds / 300, 1.0)    (5 分钟 = 满分)
    - scroll_depth: depth_pct / 100           (天然 0-1)
    - is_favorited: 0.0 或 1.0
    - annotation_count: min(count / 10, 1.0) (10 条笔记 = 满分)
"""
from __future__ import annotations

from backend.logging_config import logger
from backend.repository.db import get_connection


def score(item_id: str) -> int:
    """计算单个知识条目的注意力评分 (0-100 整数)。"""
    conn = get_connection()
    try:
        # 1. view_count — 事件计数, 20 次封顶
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM attention_events "
            "WHERE item_id = ? AND event_type = 'view'",
            (item_id,),
        ).fetchone()
        view_norm = min((row["n"] if row else 0) / 20.0, 1.0)

        # 2. dwell_time — dwell_seconds 累加, 300s 封顶
        row = conn.execute(
            "SELECT COALESCE(SUM(json_extract(detail_json, '$.dwell_seconds')), 0) AS total "
            "FROM attention_events "
            "WHERE item_id = ? AND event_type = 'dwell'",
            (item_id,),
        ).fetchone()
        dwell_norm = min((row["total"] if row else 0) / 300.0, 1.0)

        # 3. scroll_depth — depth_pct 最大值, 天然 0-100
        row = conn.execute(
            "SELECT COALESCE(MAX(json_extract(detail_json, '$.depth_pct')), 0) AS max_depth "
            "FROM attention_events "
            "WHERE item_id = ? AND event_type = 'scroll'",
            (item_id,),
        ).fetchone()
        scroll_norm = min((row["max_depth"] if row else 0) / 100.0, 1.0)

        # 4. is_favorited — 通过 url 匹配 favorites 表
        row = conn.execute(
            "SELECT 1 FROM favorites f "
            "JOIN knowledge_items k ON f.url = k.source_url "
            "WHERE k.id = ? LIMIT 1",
            (item_id,),
        ).fetchone()
        fav_norm = 1.0 if row is not None else 0.0

        # 5. annotation_count — 笔记数, 10 条封顶
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM annotations "
            "WHERE entity_type = 'knowledge_item' AND entity_id = ?",
            (item_id,),
        ).fetchone()
        ann_norm = min((row["n"] if row else 0) / 10.0, 1.0)

        # 加权求和 → 0-100
        raw = (
            view_norm * 0.25
            + dwell_norm * 0.25
            + scroll_norm * 0.15
            + fav_norm * 0.20
            + ann_norm * 0.15
        )
        return min(100, round(raw * 100))

    except Exception as e:
        logger.error(
            "attention score failed",
            extra={"trace_id": "", "item_id": item_id, "error": str(e)},
        )
        return 0


def batch_score() -> dict:
    """遍历所有知识条目, 计算并更新 attention_score。

    P1 优化: 原实现对每个 item 执行 6 次查询 (5 维 + UPDATE), 4000+ 条目
    即 24000+ 次查询 (N+1)。现改为单条聚合 SQL 一次取回全部 5 维数据,
    Python 组合评分 + executemany 批量 UPDATE (1 次查询 + 1 次批量写)。

    Returns:
        { updated: int, errors: int }
    """
    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT
                k.id AS id,
                COALESCE(v.view_n, 0)      AS view_n,
                COALESCE(d.dwell_total, 0) AS dwell_total,
                COALESCE(s.max_depth, 0)   AS max_depth,
                CASE WHEN EXISTS (
                    SELECT 1 FROM favorites f WHERE f.url = k.source_url
                ) THEN 1.0 ELSE 0.0 END    AS fav,
                COALESCE(a.ann_n, 0)       AS ann_n
            FROM knowledge_items k
            LEFT JOIN (
                SELECT item_id, COUNT(*) AS view_n FROM attention_events
                WHERE event_type = 'view' GROUP BY item_id
            ) v ON v.item_id = k.id
            LEFT JOIN (
                SELECT item_id,
                       COALESCE(SUM(json_extract(detail_json, '$.dwell_seconds')), 0) AS dwell_total
                FROM attention_events WHERE event_type = 'dwell' GROUP BY item_id
            ) d ON d.item_id = k.id
            LEFT JOIN (
                SELECT item_id,
                       COALESCE(MAX(json_extract(detail_json, '$.depth_pct')), 0) AS max_depth
                FROM attention_events WHERE event_type = 'scroll' GROUP BY item_id
            ) s ON s.item_id = k.id
            LEFT JOIN (
                SELECT entity_id, COUNT(*) AS ann_n FROM annotations
                WHERE entity_type = 'knowledge_item' GROUP BY entity_id
            ) a ON a.entity_id = k.id
            """,
        ).fetchall()
    except Exception as e:
        logger.error(
            "batch_score: failed to fetch knowledge_items",
            extra={"trace_id": "", "error": str(e)},
        )
        return {"updated": 0, "errors": 0}

    updates: list[tuple[int, str]] = []
    errors = 0
    for row in rows:
        try:
            view_norm = min(row["view_n"] / 20.0, 1.0)
            dwell_norm = min(row["dwell_total"] / 300.0, 1.0)
            scroll_norm = min(row["max_depth"] / 100.0, 1.0)
            ann_norm = min(row["ann_n"] / 10.0, 1.0)
            raw = (
                view_norm * 0.25
                + dwell_norm * 0.25
                + scroll_norm * 0.15
                + float(row["fav"]) * 0.20
                + ann_norm * 0.15
            )
            updates.append((min(100, round(raw * 100)), row["id"]))
        except Exception as e:
            logger.error(
                "batch_score: item failed",
                extra={"trace_id": "", "item_id": row["id"], "error": str(e)},
            )
            errors += 1

    if updates:
        try:
            conn.executemany(
                "UPDATE knowledge_items SET attention_score = ? WHERE id = ?",
                updates,
            )
        except Exception as e:
            logger.error(
                "batch_score: batch update failed",
                extra={"trace_id": "", "error": str(e)},
            )
            return {"updated": 0, "errors": len(updates)}

    updated = len(updates)
    logger.info(
        "batch_score completed",
        extra={"trace_id": "", "updated": updated, "errors": errors},
    )
    return {"updated": updated, "errors": errors}


__all__ = [
    "batch_score",
    "score",
]
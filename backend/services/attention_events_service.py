"""attention_events_service — 注意力事件写入/查询服务 (Batch 2 SQL 下沉).

把 /api/attention/events 路由内 3 处直连 SQL 收敛到服务层:
- INSERT attention_events (事件写入)
- SELECT knowledge_items 存在性检查 (SM-2 复习转化前置)
- 天×小时聚合 (前端 AttentionHeatmap 热力图数据源)

attention_events 表暂无 repo (Batch 3 补 AttentionEventRepository),
本服务为过渡宿主; 与 attention_scorer (只读评分) 职责分离.
依赖方向: 仅 import backend.repository.db / backend.services.review_service,
不触碰 backend.api.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection, knowledge_items_table

# 与 API 层共享的合法事件类型 (API 保留 400 校验, 此处为单一事实源)
VALID_EVENT_TYPES = frozenset({
    "view",
    "dwell",
    "scroll",
    "favorite",
    "annotation",
    "share",
})


def record_event(item_id: str, event_type: str, detail_json: dict) -> int:
    """写入一条注意力事件, 返回 event_id (lastrowid). 失败抛异常由路由映射 500."""
    detail_text = json.dumps(detail_json, ensure_ascii=False)
    created_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO attention_events "
        "(item_id, event_type, detail_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (item_id, event_type, detail_text, created_at),
    )
    return cursor.lastrowid


def maybe_create_sm2_review(
    event_type: str, item_id: str, detail_json: dict[str, Any]
) -> None:
    """P3-1: view/dwell/favorite 事件 → 自动创建 SM-2 复习记录 (幂等).

    v0.4.3 复利驱动器④: dwell 事件需 dwell_seconds > 30 才转化 (深度阅读
    判定), view/favorite 保持原有即时转化; create_review 内部幂等 (已存在
    则返回现有). item 不在 knowledge_items 时静默跳过, 任何失败仅告警不阻断.
    """
    dwell_seconds = int(detail_json.get("dwell_seconds", 0) or 0)
    if event_type == "dwell" and dwell_seconds <= 30:
        return
    if event_type not in ("view", "dwell", "favorite"):
        return
    try:
        if not knowledge_item_exists(item_id):
            return
        from backend.services.review_service import create_review

        create_review(entity_type="knowledge_item", entity_id=item_id)
    except Exception as e:
        logger.warning(f"auto-create sm2 review failed: {e}")


def knowledge_item_exists(item_id: str) -> bool:
    """知识条目是否存在 (SM-2 复习转化的前置检查)."""
    row = get_connection().execute(
        f"SELECT 1 FROM {knowledge_items_table()} WHERE id = ?",
        (item_id,),
    ).fetchone()
    return row is not None


def heatmap_by_day_hour(days: int) -> list[dict]:
    """最近 N 天按 天×小时 聚合的事件计数 (热力图数据源).

    返回 ``[{date: "YYYY-MM-DD", hour: 0-23, count: N}]``, 按 date, hour 升序.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = get_connection().execute(
        """
        SELECT substr(created_at, 1, 10) AS date,
               CAST(substr(created_at, 12, 2) AS INTEGER) AS hour,
               COUNT(*) AS count
        FROM attention_events
        WHERE created_at >= ?
        GROUP BY date, hour
        ORDER BY date, hour
        """,
        (cutoff,),
    ).fetchall()
    return [
        {"date": r["date"], "hour": r["hour"], "count": r["count"]}
        for r in rows
    ]

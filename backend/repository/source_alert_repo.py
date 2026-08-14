"""源级告警 (source_alerts) 表仓储层。

Phase 3 (Crawler v2): 源健康状态告警记录。
表结构见 migration 057_crawler_v2_phase3.sql。
"""
from __future__ import annotations

from backend.repository.db import get_connection


class SourceAlertRepository:
    """source_alerts 表 CRUD。"""

    def insert(self, alert: dict) -> int:
        """插入一条告警记录。

        Args:
            alert: 包含 source_id, alert_type, level, message, detail 的字典

        Returns:
            新插入行的 id
        """
        conn = get_connection()
        cur = conn.execute(
            """
            INSERT INTO source_alerts
                (source_id, alert_type, level, message, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                alert["source_id"],
                alert["alert_type"],
                alert.get("level", "P2"),
                alert["message"],
                alert.get("detail", ""),
            ),
        )
        return cur.lastrowid or 0

    def list(
        self,
        source_id: str | None = None,
        level: str | None = None,
        since: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """分页查询告警记录。

        Args:
            source_id: 按来源筛选
            level: 按告警级别筛选
            since: 按 created_at >= since 筛选 (ISO 时间字符串)
            page: 页码 (从 1 开始)
            page_size: 每页条数

        Returns:
            {total, page, page_size, items: [dict]} 格式的分页结果
        """
        conn = get_connection()
        conditions: list[str] = []
        params: list = []

        if source_id is not None:
            conditions.append("source_id = ?")
            params.append(source_id)
        if level is not None:
            conditions.append("level = ?")
            params.append(level)
        if since is not None:
            conditions.append("created_at >= ?")
            params.append(since)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # 总数
        row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM source_alerts {where_clause}", params
        ).fetchone()
        total = int(row["cnt"])

        # 分页数据
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM source_alerts {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [dict(r) for r in rows],
        }

    def has_recent(self, source_id: str, alert_type: str, within_hours: int = 24) -> bool:
        """检查指定来源在最近 N 小时内是否已有同类告警。

        Args:
            source_id: 来源 ID
            alert_type: 告警类型
            within_hours: 时间窗口 (小时)

        Returns:
            True 表示存在至少一条匹配记录
        """
        conn = get_connection()
        row = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM source_alerts
            WHERE source_id = ?
              AND alert_type = ?
              AND created_at >= datetime('now', ?)
            """,
            (source_id, alert_type, f"-{within_hours} hours"),
        ).fetchone()
        return int(row["cnt"]) > 0

    def get_stats(self, since_hours: int = 24) -> list[dict]:
        """按告警级别分组统计。

        Args:
            since_hours: 统计最近多少小时内的数据

        Returns:
            [{level, count}, ...]
        """
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT level, COUNT(*) as count
            FROM source_alerts
            WHERE created_at >= datetime('now', ?)
            GROUP BY level
            ORDER BY count DESC
            """,
            (f"-{since_hours} hours",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats_by_source(self, since_hours: int = 24) -> list[dict]:
        """按来源和告警类型分组统计。

        Args:
            since_hours: 统计最近多少小时内的数据

        Returns:
            [{source_id, alert_type, count}, ...]
        """
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT source_id, alert_type, COUNT(*) as count
            FROM source_alerts
            WHERE created_at >= datetime('now', ?)
            GROUP BY source_id, alert_type
            ORDER BY count DESC
            """,
            (f"-{since_hours} hours",),
        ).fetchall()
        return [dict(r) for r in rows]


__all__ = ["SourceAlertRepository"]
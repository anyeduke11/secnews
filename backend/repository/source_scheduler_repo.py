"""源调度 (crawler_sources + crawler_runs) 表仓储层。

Phase 3 (Crawler v2): 源级调度与健康管理。
表结构见 migration 055_crawler_v2_phase0.sql 和 057_crawler_v2_phase3.sql。
"""
from __future__ import annotations

from backend.repository.db import get_connection


class SourceSchedulerRepository:
    """crawler_sources 调度 + crawler_runs 统计查询。"""

    def get_schedulable(
        self, limit: int = 3, now_iso: str | None = None
    ) -> list[dict]:
        """查询当前可调度的源列表。

        cadence 修正批: 接线 ``cadence_seconds`` (此前是死列, tick 每 60s
        取 3 个源轮转, 无"距上次抓取不足 N 秒则跳过"门控)。条件与
        ``BaseCollector._load_sources_from_registry`` 同语义: last_fetch_at
        为空/不可解析 → 到期; 否则 julianday 比较 (ISO 带时区后缀 SQLite
        可解析, 避免 'T' vs ' ' 文本比较陷阱)。

        Args:
            limit: 最大返回条数
            now_iso: 当前时间 (ISO 格式)，用于冷却/节奏判断；为 None 时使用
                SQLite datetime('now') / julianday('now')

        Returns:
            list of dict，每行一条可调度源
        """
        conn = get_connection()
        if now_iso is not None:
            rows = conn.execute(
                """
                SELECT * FROM crawler_sources
                WHERE enabled = 1
                  AND status NOT IN ('dead', 'disabled')
                  AND (cooldown_until IS NULL OR cooldown_until < ?)
                  AND (last_fetch_at IS NULL OR last_fetch_at = ''
                       OR julianday(last_fetch_at) IS NULL
                       OR julianday(last_fetch_at)
                          + COALESCE(cadence_seconds, 1800) / 86400.0 <= julianday(?))
                ORDER BY priority DESC, last_fetch_at ASC
                LIMIT ?
                """,
                (now_iso, now_iso, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM crawler_sources
                WHERE enabled = 1
                  AND status NOT IN ('dead', 'disabled')
                  AND (cooldown_until IS NULL OR cooldown_until < datetime('now'))
                  AND (last_fetch_at IS NULL OR last_fetch_at = ''
                       OR julianday(last_fetch_at) IS NULL
                       OR julianday(last_fetch_at)
                          + COALESCE(cadence_seconds, 1800) / 86400.0 <= julianday('now'))
                ORDER BY priority DESC, last_fetch_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_health_state(self, source_id: str, **fields) -> bool:
        """更新源的健康状态字段。

        同时设置 updated_at = datetime('now')。

        Args:
            source_id: 源 ID
            **fields: 要更新的字段名和值（如 status='dead', consecutive_failures=3）

        Returns:
            True 表示至少更新了一行
        """
        if not fields:
            return False
        conn = get_connection()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values())
        params.append(source_id)
        cur = conn.execute(
            f"UPDATE crawler_sources SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            params,
        )
        return cur.rowcount > 0

    def get_run_stats(self, source_id: str, since_hours: int = 24) -> dict:
        """查询源在最近 N 小时内的运行统计。

        Args:
            source_id: 源 ID
            since_hours: 统计时间窗口（小时）

        Returns:
            dict 含 total_runs, failed_runs, total_fetched, total_accepted,
            avg_duration_ms, rejection_rate
        """
        conn = get_connection()
        row = conn.execute(
            """
            SELECT
                COUNT(*)                                                AS total_runs,
                COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_runs,
                COALESCE(SUM(fetched_count), 0)                         AS total_fetched,
                COALESCE(SUM(accepted_count), 0)                        AS total_accepted,
                COALESCE(CAST(AVG(duration_ms) AS REAL), 0.0)           AS avg_duration_ms
            FROM crawler_runs
            WHERE source_id = ?
              AND started_at >= datetime('now', ?)
            """,
            (source_id, f"-{since_hours} hours"),
        ).fetchone()

        total_fetched = int(row["total_fetched"])
        total_accepted = int(row["total_accepted"])
        rejection_rate = (
            (total_fetched - total_accepted) / total_fetched
            if total_fetched > 0
            else 0.0
        )

        return {
            "total_runs": int(row["total_runs"]),
            "failed_runs": int(row["failed_runs"]),
            "total_fetched": total_fetched,
            "total_accepted": total_accepted,
            "avg_duration_ms": round(float(row["avg_duration_ms"]), 2),
            "rejection_rate": round(rejection_rate, 4),
        }

    def get_by_id(self, source_id: str) -> dict | None:
        """按 ID 查询单条源记录。

        Args:
            source_id: 源 ID

        Returns:
            dict 或 None
        """
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM crawler_sources WHERE id = ?", (source_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_all(self) -> list[dict]:
        """返回所有源记录，按 category 分组、priority 降序排列。

        Returns:
            list of dict
        """
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM crawler_sources ORDER BY category, priority DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats_summary(self) -> dict:
        """返回源健康状态汇总统计。

        P5-3: 增加 unknown 计数 (seed 初始态), 避免口径失真。

        Returns:
            dict 含 total, active, grace, stale, dead, unknown, disabled,
            active_rate
        """
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS cnt
            FROM crawler_sources
            GROUP BY status
            """
        ).fetchall()

        counts: dict[str, int] = {}
        for r in rows:
            counts[r["status"]] = int(r["cnt"])

        total = sum(counts.values())
        active = counts.get("active", 0)
        grace = counts.get("grace", 0)
        stale = counts.get("stale", 0)
        dead = counts.get("dead", 0)
        unknown = counts.get("unknown", 0)
        disabled = counts.get("disabled", 0)
        active_rate = round(active / total, 4) if total > 0 else 0.0

        return {
            "total": total,
            "active": active,
            "grace": grace,
            "stale": stale,
            "dead": dead,
            "unknown": unknown,
            "disabled": disabled,
            "active_rate": active_rate,
        }


__all__ = ["SourceSchedulerRepository"]
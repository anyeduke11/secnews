"""Repository for ``source_stats`` and ``coverage_runs`` tables.

数据模型 (Phase 9 招标源质量门禁)
---------------------------------
每个 (category, source_name) 1 行，统计该源：

- 累计 collect 次数 (``total_runs``)
- 连续零产出次数 (``zero_yield_runs``)
- 累计产出 items 数 (``total_items``)
- 最近一次产出时间 (``last_seen_at``) / 最近一次 collect 跑过该源的时间 (``last_checked_at``)
- 健康状态 ``status`` ∈ {``active``, ``stale``, ``dead``}

阈值从 ``settings`` 表读取，可被运维热更新：
- ``quality.coverage_max_zero_yield_runs`` (默认 3) → 降级 stale
- ``quality.coverage_dead_threshold`` (默认 6) → 降级 dead（连续零产出轮次）
- ``quality.coverage_dead_min_hours`` (默认 72) → 判死的**时间下限**：距最近一次
  产出不足该时长不判死。轮次阈值单独用会误杀低频发布源（政府招标站夜间/周末不
  发布，实测 17 分钟一轮 × 6 ≈ 1.7 小时即被判死，导致 bid 类 64/64 全 dead）。
- ``quality.coverage_min_active_sources`` (默认 3) → 覆盖度告警阈值

``status`` 是"最近是否有产出"的函数，**可双向迁移**：有产出即回 active。
历史实现的单向棘轮（只升不降）会让永久停在 dead 的源即使当轮采集成功也无法
复活，详见 ``upsert_after_run`` 内注释。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _idle_exceeds(last_seen: Any, now_iso: str, min_hours: int) -> bool:
    """距最近一次产出是否已超过 ``min_hours`` 小时。

    ``last_seen`` 为空 = 该源从未产出过, 没有"产出节奏"可言 → 返回 True, 让轮次
    阈值继续生效。时间戳无法解析时同样返回 True (退回按轮次判死的旧语义), 避免
    脏数据让故障源永远不被判死。
    """
    if not last_seen:
        return True
    try:
        seen = datetime.fromisoformat(str(last_seen))
        now = datetime.fromisoformat(now_iso)
    except (TypeError, ValueError):
        return True
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - seen).total_seconds() >= min_hours * 3600


# ---------------------------------------------------------------------------
# SourceStatsRepository
# ---------------------------------------------------------------------------
class SourceStatsRepository:
    """每个数据源累计产出 + 健康状态。"""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def upsert_after_run(
        self,
        category: str,
        source_name: str,
        source_url: str,
        item_count: int,
        error_msg: str | None = None,
    ) -> None:
        """collect 完一条 source 后调用，累加统计并按阈值升级 status。

        Parameters
        ----------
        category:
            Category enum value (e.g. ``"bid"``).
        source_name:
            源名 (例如 ``"中国政府采购网"``).
        source_url:
            源 URL.
        item_count:
            本次 collect 产出的 item 数。>= 1 视为有产出。
        error_msg:
            本次 collect 的错误信息 (无错为 ``None``).

        副作用
        ------
        ``zero_yield_runs`` 在 item_count == 0 时 +1，否则归零。
        ``status`` 在 ``zero_yield_runs`` 跨过阈值时升级 (``active`` → ``stale`` → ``dead``)。
        """
        if not category or not source_name:
            return
        now = _now_iso()
        produced = item_count >= 1
        conn = get_connection()
        # 读当前 row（如果存在）
        cur = conn.execute(
            "SELECT zero_yield_runs, total_runs, total_items, status, last_seen_at "
            "FROM source_stats WHERE category = ? AND source_name = ?",
            (category, source_name),
        )
        row = cur.fetchone()
        if row is None:
            new_zr = 0 if produced else 1
            new_status = "active" if produced else "active"  # 首次连 0 不升级
            new_total_runs = 1
            new_total_items = item_count
            try:
                conn.execute(
                    "INSERT INTO source_stats ("
                    "  category, source_name, source_url,"
                    "  last_seen_at, last_checked_at,"
                    "  total_runs, zero_yield_runs, total_items,"
                    "  last_error, status, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        category,
                        source_name,
                        source_url,
                        now if produced else None,
                        now,
                        new_total_runs,
                        new_zr,
                        new_total_items,
                        error_msg,
                        new_status,
                        now,
                    ),
                )
            except sqlite3.Error as e:
                logger.warning(
                    "source_stats insert failed",
                    extra={
                        "trace_id": "",
                        "category": category,
                        "source": source_name,
                        "error": str(e),
                    },
                )
            return

        # 已存在 → 更新
        prev_zr = int(row["zero_yield_runs"] or 0)
        prev_total_runs = int(row["total_runs"] or 0)
        prev_total_items = int(row["total_items"] or 0)
        prev_status = str(row["status"] or "active")

        new_zr = 0 if produced else prev_zr + 1
        new_total_runs = prev_total_runs + 1
        new_total_items = prev_total_items + item_count

        # 阈值读取
        try:
            max_zr = int(_get_setting(conn, "quality.coverage_max_zero_yield_runs", "3"))
            dead_thr = int(_get_setting(conn, "quality.coverage_dead_threshold", "6"))
            dead_min_hours = int(
                _get_setting(conn, "quality.coverage_dead_min_hours", "72")
            )
        except Exception:
            max_zr = 3
            dead_thr = 6
            dead_min_hours = 72

        # 状态机: status 必须是"最近是否有产出"的函数, 可双向迁移。
        # 历史实现为 `new_status = prev_status` + 注释"不会主动降级", 使 dead 成为
        # 单向棘轮: 当轮产出使 new_zr=0 后两个分支都不再命中, 源会永久停在 dead。
        # 实测 16 个源带产出仍显示 dead (FreeBuf total_items=66968, last_seen 距
        # 本次写入不足 1 分钟), 直接导致前端"119 离线"失真。
        if produced:
            new_status = "active"
        else:
            new_status = prev_status
            # 判死需同时满足"连续零产出轮次"与"距上次产出足够久", 否则低频发布源
            # (政府招标站夜间/周末不发布) 会被轮次阈值误杀: 17min/轮 × 6 ≈ 1.7h。
            # 从未产出过的源没有 last_seen_at 可依, 按轮次判死 (含解析器从未生效)。
            if new_zr >= dead_thr and _idle_exceeds(row["last_seen_at"], now, dead_min_hours):
                new_status = "dead"
            elif new_zr >= max_zr and prev_status == "active":
                new_status = "stale"

        last_seen = now if produced else None
        try:
            conn.execute(
                "UPDATE source_stats SET "
                "  source_url = ?, "
                "  last_seen_at = COALESCE(?, last_seen_at), "
                "  last_checked_at = ?, "
                "  total_runs = ?, "
                "  zero_yield_runs = ?, "
                "  total_items = ?, "
                "  last_error = ?, "
                "  status = ?, "
                "  updated_at = ? "
                "WHERE category = ? AND source_name = ?",
                (
                    source_url,
                    last_seen,
                    now,
                    new_total_runs,
                    new_zr,
                    new_total_items,
                    error_msg,
                    new_status,
                    now,
                    category,
                    source_name,
                ),
            )
        except sqlite3.Error as e:
            logger.warning(
                "source_stats update failed",
                extra={
                    "trace_id": "",
                    "category": category,
                    "source": source_name,
                    "error": str(e),
                },
            )

    def mark_dead(self, category: str, source_name: str) -> None:
        """手动标 dead（运维工具调用）。"""
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE source_stats SET status = 'dead', updated_at = ? "
                "WHERE category = ? AND source_name = ?",
                (_now_iso(), category, source_name),
            )
        except sqlite3.Error as e:
            raise InternalException(f"mark_dead failed: {e}") from e

    def reset(self, category: str, source_name: str) -> None:
        """手动 reset zero_yield_runs（运维工具调用）。"""
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE source_stats SET zero_yield_runs = 0, status = 'active', "
                "  updated_at = ? "
                "WHERE category = ? AND source_name = ?",
                (_now_iso(), category, source_name),
            )
        except sqlite3.Error as e:
            raise InternalException(f"reset failed: {e}") from e

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def get_one(
        self, category: str, source_name: str
    ) -> dict[str, Any] | None:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM source_stats "
                "WHERE category = ? AND source_name = ?",
                (category, source_name),
            ).fetchone()
        except sqlite3.Error as e:
            raise InternalException(f"source_stats get_one failed: {e}") from e
        if row is None:
            return None
        return dict(row)

    def list_by_category(self, category: str) -> list[dict[str, Any]]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM source_stats WHERE category = ? "
                "ORDER BY status ASC, zero_yield_runs DESC, source_name ASC",
                (category,),
            ).fetchall()
        except sqlite3.Error as e:
            raise InternalException(
                f"source_stats list_by_category failed: {e}"
            ) from e
        return [dict(r) for r in rows]

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM source_stats WHERE status = ? "
                "ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        except sqlite3.Error as e:
            raise InternalException(
                f"source_stats list_by_status failed: {e}"
            ) from e
        return [dict(r) for r in rows]

    def list_all(self) -> list[dict[str, Any]]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM source_stats "
                "ORDER BY category ASC, status ASC, source_name ASC"
            ).fetchall()
        except sqlite3.Error as e:
            raise InternalException(f"source_stats list_all failed: {e}") from e
        return [dict(r) for r in rows]

    def summary_by_category(self) -> dict[str, dict[str, int]]:
        """按 category 聚合：active / stale / dead / total 计数。"""
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT category, status, COUNT(*) AS n "
                "FROM source_stats GROUP BY category, status"
            ).fetchall()
        except sqlite3.Error as e:
            raise InternalException(
                f"source_stats summary_by_category failed: {e}"
            ) from e
        out: dict[str, dict[str, int]] = {}
        for r in rows:
            cat = r["category"]
            out.setdefault(cat, {"active": 0, "stale": 0, "dead": 0, "total": 0})
            out[cat][r["status"]] = int(r["n"])
            out[cat]["total"] = sum(
                int(v) for k, v in out[cat].items() if k != "total"
            )
        return out


# ---------------------------------------------------------------------------
# CoverageRunRepository
# ---------------------------------------------------------------------------
class CoverageRunRepository:
    """``coverage_runs`` 表 — 每次 collect 跑完后的源覆盖度快照。"""

    def write_run(
        self,
        run_id: str,
        category: str,
        total_sources: int,
        active_sources: int,
        zero_sources: int,
        details: list[dict[str, Any]],
    ) -> int:
        """写入 1 行覆盖度快照。返回 rowid。"""
        conn = get_connection()
        coverage_ratio = (
            float(active_sources) / float(total_sources)
            if total_sources > 0
            else 0.0
        )
        try:
            cur = conn.execute(
                "INSERT INTO coverage_runs ("
                "  run_id, category, total_sources, active_sources, "
                "  zero_sources, coverage_ratio, details_json, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    category,
                    total_sources,
                    active_sources,
                    zero_sources,
                    coverage_ratio,
                    json.dumps(details, ensure_ascii=False),
                    _now_iso(),
                ),
            )
            return int(cur.lastrowid or 0)
        except sqlite3.Error as e:
            raise InternalException(f"coverage_runs write failed: {e}") from e

    def latest_for_category(
        self, category: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM coverage_runs WHERE category = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        except sqlite3.Error as e:
            raise InternalException(
                f"coverage_runs latest failed: {e}"
            ) from e
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["details"] = json.loads(d.pop("details_json", "[]"))
            except Exception:
                d["details"] = []
            out.append(d)
        return out


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------
def _get_setting(conn, key: str, default: str) -> str:
    """从 settings 表读 value，缺失或失败返回 default。"""
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row and row["value"] is not None:
            return str(row["value"])
    except sqlite3.Error:
        pass
    return default


__all__ = ["CoverageRunRepository", "SourceStatsRepository"]

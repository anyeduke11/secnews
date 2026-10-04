"""Repository for ``quality_check_logs`` and ``source_reputation`` tables.

Used by the quality pipeline + scheduler jobs to persist gate outcomes
and to read / write per-source reputation scores.

Both tables are added in ``002_quality.sql`` (Phase 3.5). All writes
happen via explicit ``BEGIN``/``COMMIT`` (autocommit connection).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.domain.collection import GateResult
from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection, warm_table


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class QualityLogRepository:
    """Persistence for ``quality_check_logs``."""

    def write_log(
        self,
        item_id: str,
        result: GateResult,
        mode: str = "loose",
        checked_at: str | None = None,
    ) -> None:
        """写一行 gate 结果。**失败不抛**（写 log 失败不能阻塞采集）。

        P0-7 (审计 E15): 表名走 ``warm_table`` accessor — 生产表在 warm,
        单库模式在 main, 裸名依赖 SQLite 环境探测的路由历史上有
        "no such table" 静默失败窗口。
        """
        conn = get_connection()
        try:
            # 解析也在 try 内: 模拟/异常连接下同样不得抛 (does-not-throw 契约)
            sql = (
                f"INSERT INTO {warm_table('quality_check_logs', conn)} "
                "(item_id, gate_name, passed, score_deduction, flags, "
                "reason, error_msg, checked_at, mode) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            conn.execute(
                sql,
                (
                    item_id,
                    result.gate_name,
                    1 if result.passed else 0,
                    result.score_deduction,
                    json.dumps(result.flags or [], ensure_ascii=False),
                    result.reason,
                    result.error_msg,
                    checked_at or _now_iso(),
                    mode,
                ),
            )
        except Exception as e:
            logger.warning(
                "write quality log failed",
                extra={
                    "trace_id": "",
                    "item_id": item_id,
                    "gate": result.gate_name,
                    "error": str(e),
                },
            )

    def list_rejections(
        self, *, hours: int = 168, limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """P1-5 拒收回放 (审计 F1-3): 拒收标记行 LEFT JOIN raw_items 原文。

        gate_name='pipeline' AND passed=0 = strict 模式真实拒收 (hard gate
        fail 或 final_score < min_score, 由 pipeline 在 raise 前写标记)。
        LEFT JOIN: raw_items 缺失时 raw 为 None — UI 诚实显示"原文未留存",
        不伪造。两表均走 warm_table accessor (生产在 warm, 单库模式 main)。
        """
        conn = get_connection()
        qcl = warm_table("quality_check_logs", conn)
        raw = warm_table("raw_items", conn)
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()
        where = "l.gate_name = 'pipeline' AND l.passed = 0 AND l.checked_at >= ?"
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM {qcl} l WHERE {where}", (cutoff,),
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT l.item_id, l.gate_name, l.score_deduction, l.flags, "
                f"l.reason, l.error_msg, l.checked_at, l.mode, "
                f"r.title AS raw_title, r.url AS raw_url, "
                f"r.summary AS raw_summary, r.source_id AS raw_source_id, "
                f"r.published_at AS raw_published_at "
                f"FROM {qcl} l LEFT JOIN {raw} r ON r.item_id = l.item_id "
                f"WHERE {where} ORDER BY l.checked_at DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
        except sqlite3.Error as e:
            raise InternalException(f"list_rejections failed: {e}") from e
        items: list[dict[str, Any]] = []
        for r in rows:
            flags_raw = r["flags"]
            has_raw = r["raw_title"] is not None or r["raw_url"] is not None
            items.append({
                "item_id": r["item_id"],
                "gate_name": r["gate_name"],
                "score_deduction": r["score_deduction"],
                "flags": json.loads(flags_raw) if flags_raw else [],
                "reason": r["reason"],
                "error_msg": r["error_msg"],
                "checked_at": r["checked_at"],
                "mode": r["mode"],
                "raw": {
                    "title": r["raw_title"],
                    "url": r["raw_url"],
                    "summary": r["raw_summary"],
                    "source_id": r["raw_source_id"],
                    "published_at": r["raw_published_at"],
                } if has_raw else None,
            })
        return items, total

    def list_for_item(self, item_id: str, limit: int = 50) -> list[dict]:
        """返回该 item 的最近 N 条检查记录。"""
        conn = get_connection()
        table = warm_table("quality_check_logs", conn)
        try:
            rows = conn.execute(
                f"SELECT gate_name, passed, score_deduction, flags, reason, "
                f"error_msg, checked_at, mode "
                f"FROM {table} "
                f"WHERE item_id = ? "
                f"ORDER BY checked_at DESC LIMIT ?",
                (item_id, limit),
            ).fetchall()
        except sqlite3.Error as e:
            raise InternalException(f"list_for_item failed: {e}") from e

        out: list[dict] = []
        for r in rows:
            flags_raw = r["flags"]
            out.append(
                {
                    "gate_name": r["gate_name"],
                    "passed": bool(r["passed"]),
                    "score_deduction": r["score_deduction"],
                    "flags": json.loads(flags_raw) if flags_raw else [],
                    "reason": r["reason"],
                    "error_msg": r["error_msg"],
                    "checked_at": r["checked_at"],
                    "mode": r["mode"],
                }
            )
        return out

    def summary_24h(self) -> dict[str, dict[str, Any]]:
        """24h 内每个 gate 的 pass/fail 统计 + 平均扣分。"""
        conn = get_connection()
        table = warm_table("quality_check_logs", conn)
        try:
            rows = conn.execute(
                f"SELECT gate_name, "
                f"  SUM(passed) AS pass_n, "
                f"  COUNT(*) AS total_n, "
                f"  AVG(score_deduction) AS avg_deduction "
                f"FROM {table} "
                f"WHERE checked_at >= datetime('now', '-24 hours') "
                f"GROUP BY gate_name"
            ).fetchall()
        except sqlite3.Error as e:
            raise InternalException(f"summary_24h failed: {e}") from e

        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            out[r["gate_name"]] = {
                "pass": int(r["pass_n"] or 0),
                "total": int(r["total_n"] or 0),
                "avg_deduction": float(r["avg_deduction"] or 0.0),
            }
        return out


class SourceReputationRepository:
    """Persistence for ``source_reputation``."""

    def get(self, source: str) -> dict[str, Any] | None:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT source, score, blacklist, last_updated, "
                "pass_count, fail_count "
                "FROM source_reputation WHERE source = ?",
                (source,),
            ).fetchone()
        except sqlite3.Error as e:
            raise InternalException(f"source_reputation get failed: {e}") from e
        if row is None:
            return None
        return {
            "source": row["source"],
            "score": row["score"],
            "blacklist": bool(row["blacklist"]),
            "last_updated": row["last_updated"],
            "pass_count": row["pass_count"],
            "fail_count": row["fail_count"],
        }

    def get_many(self, sources: list[str]) -> dict[str, dict[str, Any]]:
        """批量读；缺失的 source 不会出现在结果里。"""
        if not sources:
            return {}
        conn = get_connection()
        placeholders = ",".join("?" for _ in sources)
        try:
            rows = conn.execute(
                f"SELECT source, score, blacklist, last_updated, "
                f"pass_count, fail_count FROM source_reputation "
                f"WHERE source IN ({placeholders})",
                list(sources),
            ).fetchall()
        except sqlite3.Error as e:
            raise InternalException(
                f"source_reputation get_many failed: {e}"
            ) from e

        return {
            row["source"]: {
                "source": row["source"],
                "score": row["score"],
                "blacklist": bool(row["blacklist"]),
                "last_updated": row["last_updated"],
                "pass_count": row["pass_count"],
                "fail_count": row["fail_count"],
            }
            for row in rows
        }

    def upsert(
        self,
        source: str,
        score: int,
        blacklist: int,
        pass_count: int,
        fail_count: int,
    ) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO source_reputation "
                "(source, score, blacklist, last_updated, pass_count, fail_count) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source) DO UPDATE SET "
                "  score = excluded.score, "
                "  blacklist = excluded.blacklist, "
                "  last_updated = excluded.last_updated, "
                "  pass_count = excluded.pass_count, "
                "  fail_count = excluded.fail_count",
                (
                    source,
                    score,
                    blacklist,
                    _now_iso(),
                    pass_count,
                    fail_count,
                ),
            )
        except sqlite3.Error as e:
            raise InternalException(
                f"source_reputation upsert failed: {e}"
            ) from e

    def rebuild_all(self) -> int:
        """从 quality_check_logs 重新算每个 source 的评分 (v4.4 增强).

        vs 旧实现 (2026-08-20):
          - 只统计「质量型 gate」: schema / noise / duplicate / content_hash /
            recency 属"结构性信号"(重复与否不反映源质量),
            不再计入 source 声誉 —— 否则 duplicate 高的源被错误降分。
            (bid_recency 门已随标讯下线移除, DEV-0183)
          - 统计 gate: title_summary / category_match / source_reputation /
            AuthorVerification / FinalUrl / content / url_content /
            url_validity (真正反映"这条素材好不好")。

        score = 100 - 100 * fail_count / (pass + fail + 1)
        blacklist = (fail > 100 AND score < 30) ? 1 : 0

        Returns the number of distinct sources updated.
        """
        conn = get_connection()
        qcl = warm_table("quality_check_logs", conn)
        # 质量型 gate 白名单（排除结构性/去重信号）
        quality_gates = (
            "title_summary", "category_match", "source_reputation",
            "AuthorVerification", "FinalUrl", "content", "url_content",
            "url_validity",
        )
        placeholders = ",".join("?" for _ in quality_gates)
        try:
            rows = conn.execute(
                f"SELECT h.source, "
                f"  SUM(CASE WHEN q.passed = 1 THEN 1 ELSE 0 END) AS pass_n, "
                f"  SUM(CASE WHEN q.passed = 0 THEN 1 ELSE 0 END) AS fail_n "
                f"FROM {qcl} q "
                f"JOIN hotspots h ON h.id = q.item_id "
                f"WHERE q.checked_at >= datetime('now', '-7 days') "
                f"  AND q.gate_name IN ({placeholders}) "
                f"GROUP BY h.source",
                quality_gates,
            ).fetchall()
        except sqlite3.Error as e:
            raise InternalException(
                f"source_reputation rebuild_all query failed: {e}"
            ) from e

        now = _now_iso()
        n = 0
        for r in rows:
            pass_n = int(r["pass_n"] or 0)
            fail_n = int(r["fail_n"] or 0)
            score = max(0, 100 - 100 * fail_n // max(1, pass_n + fail_n + 1))
            blacklist = 1 if (fail_n > 100 and score < 30) else 0
            try:
                conn.execute(
                    "INSERT INTO source_reputation "
                    "(source, score, blacklist, last_updated, pass_count, fail_count) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(source) DO UPDATE SET "
                    "  score = excluded.score, "
                    "  blacklist = excluded.blacklist, "
                    "  last_updated = excluded.last_updated, "
                    "  pass_count = excluded.pass_count, "
                    "  fail_count = excluded.fail_count",
                    (
                        r["source"],
                        score,
                        blacklist,
                        now,
                        pass_n,
                        fail_n,
                    ),
                )
                n += 1
            except sqlite3.Error as e:
                logger.warning(
                    "source_reputation upsert failed",
                    extra={"trace_id": "", "source": r["source"], "error": str(e)},
                )
        return n


__all__ = ["QualityLogRepository", "SourceReputationRepository"]

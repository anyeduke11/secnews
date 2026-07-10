"""Repository for ``quality_check_logs`` and ``source_reputation`` tables.

Used by the quality pipeline + scheduler jobs to persist gate outcomes
and to read / write per-source reputation scores.

Both tables are added in ``002_quality.sql`` (Phase 3.5). All writes
happen via explicit ``BEGIN``/``COMMIT`` (autocommit connection).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from backend.domain.collection import GateResult
from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class QualityLogRepository:
    """Persistence for ``quality_check_logs``."""

    def write_log(
        self,
        item_id: str,
        result: GateResult,
        mode: str = "loose",
        checked_at: Optional[str] = None,
    ) -> None:
        """写一行 gate 结果。**失败不抛**（写 log 失败不能阻塞采集）。"""
        conn = get_connection()
        sql = (
            "INSERT INTO quality_check_logs "
            "(item_id, gate_name, passed, score_deduction, flags, "
            "reason, error_msg, checked_at, mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        try:
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

    def list_for_item(self, item_id: str, limit: int = 50) -> list[dict]:
        """返回该 item 的最近 N 条检查记录。"""
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT gate_name, passed, score_deduction, flags, reason, "
                "error_msg, checked_at, mode "
                "FROM quality_check_logs "
                "WHERE item_id = ? "
                "ORDER BY checked_at DESC LIMIT ?",
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
        try:
            rows = conn.execute(
                "SELECT gate_name, "
                "  SUM(passed) AS pass_n, "
                "  COUNT(*) AS total_n, "
                "  AVG(score_deduction) AS avg_deduction "
                "FROM quality_check_logs "
                "WHERE checked_at >= datetime('now', '-24 hours') "
                "GROUP BY gate_name"
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

    def get(self, source: str) -> Optional[dict[str, Any]]:
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
        """从 quality_check_logs 重新算每个 source 的评分。

        Returns the number of distinct sources updated.

        score = 100 - 100 * fail_count / (pass + fail + 1)
        blacklist = (fail > 100 AND score < 30) ? 1 : 0
        """
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT h.source, "
                "  SUM(CASE WHEN q.passed = 1 THEN 1 ELSE 0 END) AS pass_n, "
                "  SUM(CASE WHEN q.passed = 0 THEN 1 ELSE 0 END) AS fail_n "
                "FROM quality_check_logs q "
                "JOIN hotspots h ON h.id = q.item_id "
                "WHERE q.checked_at >= datetime('now', '-7 days') "
                "GROUP BY h.source"
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

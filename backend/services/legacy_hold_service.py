"""v1.0 T09 F01 修复 — LegacyHoldService (53 pending → legacy_hold).

对应 V0.8.3_CRITICAL_REVIEW §F01 + EXECUTION_GUIDE §4 T09 通过证据:

  - 查 trigger_tickets 表 status='pending' 的所有票据 (v0.8 阶段遗留下的 53 条)
  - 改 status='legacy_hold' (新 status, migration 099 已扩展 CHECK 约束)
  - 落 audit_log (action='ticket.legacy_hold', actor='system:legacy_hold')
  - **不删原行, 只改 status** — T16 旧数据迁移时反查 (避免丢失票据身份)
  - 幂等: 重复跑不重复标 (UPDATE WHERE status='pending' 影响行数 = 0 时不动 audit)

设计纪律:
  - 隔离 conftest 下走 temp_db (T01 已落地); 默认 process-wide conn
  - 单测可注入 conn (与 v1_evidence_service / worker_coordinator 风格一致)
  - 不引入新依赖, 不动 v0.8 trigger_gate 已有代码
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection

# ---------------------------------------------------------------------------
# F01 收口常量
# ---------------------------------------------------------------------------
LEGACY_HOLD_STATUS = "legacy_hold"
LEGACY_HOLD_REASON = (
    "F01 53 pending tickets 无关联 run, v0.8.3 治理批次; "
    "留 T16 旧数据迁移再处理"
)
LEGACY_HOLD_ACTOR = "system:legacy_hold"
LEGACY_HOLD_ACTION = "ticket.legacy_hold"


@dataclass
class LegacyHoldResult:
    """F01 收口单次执行结果 — 调度方 / 测试断言共用."""

    candidate_count: int
    reclassified_count: int
    audit_log_count: int
    started_at: str
    finished_at: str
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_count": self.candidate_count,
            "reclassified_count": self.reclassified_count,
            "audit_log_count": self.audit_log_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
        }


class LegacyHoldService:
    """F01 收口服务 — 把 pending 票据批量改 status='legacy_hold' + audit_log 留痕.

    调用方:
      - scheduler job 54 `legacy_hold_reap` (周一 04:30 一次)
      - 手动命令 / 一次性脚本 (修复阶段用)

    幂等语义:
      - candidate_count = 当前 status='pending' 的总条数 (SELECT COUNT)
      - reclassified_count = UPDATE WHERE status='pending' 影响行数
      - 第二次跑: candidate 仍可能 > 0 (新提交的 pending), 但 reclassified 仅算新增
      - audit_log_count = 本次新插 audit_log 条数 (与 reclassified 一致)

    失败语义:
      - DB 异常 → 抛 (scheduler job 用 try/except 兜底, 不死循环)
      - audit_log 落失败 → 抛 (与 trigger_tickets UPDATE 同事务, 全成功或全失败)
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn or get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def reap_pending_tickets(
        self,
        reason: str = LEGACY_HOLD_REASON,
    ) -> LegacyHoldResult:
        """收口所有 status='pending' 的票据.

        Parameters
        ----------
        reason:
            落 audit_log 的 reason (默认 F01 治理批次原因).

        Returns
        -------
        LegacyHoldResult — 含 candidate_count / reclassified_count / audit_log_count.
        """
        import time

        t0 = time.time()
        started_at = datetime.now(timezone.utc).isoformat()

        with self._tx() as conn:
            # 1) 候选条数 (含本次不会重分类的 — 仅做观测统计)
            candidate_count = conn.execute(
                "SELECT COUNT(*) FROM trigger_tickets WHERE status = ?",
                ("pending",),
            ).fetchone()[0]

            # 2) UPDATE pending → legacy_hold (幂等: WHERE status='pending' 限定)
            cur = conn.execute(
                "UPDATE trigger_tickets SET status = ?, error = ? "
                "WHERE status = ?",
                (
                    LEGACY_HOLD_STATUS,
                    f"legacy_hold: {reason}",
                    "pending",
                ),
            )
            reclassified_count = cur.rowcount

            # 3) audit_log 留痕 (每条受影响票据一条)
            audit_log_count = 0
            if reclassified_count > 0:
                # 只审计本次新转 legacy_hold 的行 — 按 enqueued_at 取最新 reclassified_count 条
                # (SQLite UPDATE 影响行无内置 RETURNING, 走 SELECT id ORDER BY id DESC LIMIT N 反查)
                rows = conn.execute(
                    "SELECT ticket_id, target_type, target_id FROM trigger_tickets "
                    "WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (LEGACY_HOLD_STATUS, reclassified_count),
                ).fetchall()
                for row in rows:
                    conn.execute(
                        "INSERT INTO audit_log "
                        "(actor, action, target, detail, occurred_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            LEGACY_HOLD_ACTOR,
                            LEGACY_HOLD_ACTION,
                            f"trigger_ticket:{row['ticket_id']}",
                            json.dumps(
                                {
                                    "target_type": row["target_type"],
                                    "target_id": row["target_id"],
                                    "reason": reason,
                                    "previous_status": "pending",
                                    "new_status": LEGACY_HOLD_STATUS,
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    audit_log_count += 1

        finished_at = datetime.now(timezone.utc).isoformat()
        duration_ms = int((time.time() - t0) * 1000)
        result = LegacyHoldResult(
            candidate_count=candidate_count,
            reclassified_count=reclassified_count,
            audit_log_count=audit_log_count,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
        )
        logger.info(
            "legacy_hold reap: candidates={} reclassified={} audit={} duration_ms={}",
            candidate_count,
            reclassified_count,
            audit_log_count,
            duration_ms,
        )
        return result

    # ------------------------------------------------------------------
    # 查询 (测试 / 观测用)
    # ------------------------------------------------------------------
    def list_legacy_hold_tickets(self, limit: int = 100) -> list[dict[str, Any]]:
        """列 status='legacy_hold' 的票据 — T16 旧数据迁移的反查入口."""
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT ticket_id, target_type, target_id, source, enqueued_at, "
                "attempts, error FROM trigger_tickets WHERE status = ? "
                "ORDER BY id DESC LIMIT ?",
                (LEGACY_HOLD_STATUS, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_legacy_hold_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        """列 ticket.legacy_hold 的 audit_log 记录."""
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT id, actor, action, target, detail, occurred_at FROM audit_log "
                "WHERE action = ? ORDER BY id DESC LIMIT ?",
                (LEGACY_HOLD_ACTION, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict[str, int]:
        """trigger_tickets 按 status 统计 (供观测 — 含 legacy_hold 键)."""
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS c FROM trigger_tickets GROUP BY status"
            ).fetchall()
        return {r["status"]: r["c"] for r in rows}


__all__ = [
    "LEGACY_HOLD_ACTION",
    "LEGACY_HOLD_ACTOR",
    "LEGACY_HOLD_REASON",
    "LEGACY_HOLD_STATUS",
    "LegacyHoldResult",
    "LegacyHoldService",
]

"""skill_runner.result — SkillRunResult 数据类 + skill_runs 表 DAO (B2).

设计要点:
- ``SkillRunResult`` 是 run 的返回值数据类, 含 run_id (skill_runs 主键) /
  status / outputs / metrics / wiki_path / llm_tokens 全字段 (R3).
- ``SkillRunRepo`` 是 skill_runs 表的薄封装 (单例友好), 字段与 migration 091
  一一对齐; 写路径全部走 INSERT OR REPLACE 幂等 (崩溃恢复可重复写).

非目标 (B2 不做):
- 读路径分页 / 复杂过滤 — RunHistory/Dashboard 留 B6 单独实现.
- 反馈打分 (feedback_log) — B3 agent_memory 接管, 写路径只留 skill_run_id 引用.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.repository.db import get_connection


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _now_localtime() -> str:
    """localtime 'YYYY-MM-DD HH:MM:SS' 形式 — 与 migration 091 默认 datetime 一致."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_dump(obj: Any) -> str:
    """JSON 序列化 (中文/unicode 保真). 写 SQLite TEXT 列."""
    return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------------------
# SkillRunResult — run 返回值数据类
# ---------------------------------------------------------------------------
@dataclass
class SkillRunResult:
    """一次 skill 跑的实际结果 (B2 R3 统一数据源).

    字段:
        run_id:       skill_runs 主键 (UUID/ULID 字符串, 全局唯一)
        skill_id:     被跑的 skill id (kebab-case, 与 SkillDef.id 对齐)
        ticket_id:    trigger_tickets.ticket_id (可空, 内部直跑也允许)
        status:       'succeeded' / 'partial' / 'failed' (终态)
        fast_path:    True = A/B 走 fast-path; False = C/D 走完整五阶段
        outputs:      pipeline 各阶段产物的聚合 (skill-specific dict)
        wiki_path:    C 类产物 wiki 路径 (如 llm-wiki-2.0/ops/2026-09-04-top5.md);
                      A/B/D 类为空
        llm_tokens:   累计 LLM token (A/B = 0, fast-path 承诺)
        elapsed_ms:    端到端耗时
        metrics:      额外指标 dict (phase_count / error 等)
        error:        失败时的简短错误描述 (partial 路径下为 None)
    """

    run_id: str
    skill_id: str
    ticket_id: str | None = None
    status: str = "succeeded"
    fast_path: bool = False
    outputs: dict[str, Any] = field(default_factory=dict)
    wiki_path: str | None = None
    llm_tokens: int = 0
    elapsed_ms: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_metrics(self) -> dict[str, Any]:
        """拼成 metrics 列要存的 dict (含本数据类扁平字段)."""
        return {
            "elapsed_ms": self.elapsed_ms,
            "llm_tokens": self.llm_tokens,
            "fast_path": self.fast_path,
            "wiki_path": self.wiki_path,
            **self.metrics,
        }


# ---------------------------------------------------------------------------
# SkillRunRepo — skill_runs 表 DAO
# ---------------------------------------------------------------------------
class SkillRunRepo:
    """skill_runs 写薄封装 (单例友好, 不持连接, 走 thread-local).

    所有写路径幂等 (INSERT OR REPLACE); read_by_id / list_for_skill 仅返回
    必要字段, 排序按时间倒序 (RunHistory 直接消费).
    """

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def insert(
        self,
        run_id: str,
        *,
        skill_id: str,
        ticket_id: str | None,
        status: str,
        phase: str | None = None,
        inputs: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        error: str | None = None,
        finished: bool = False,
    ) -> None:
        """插入一条 run (幂等 INSERT OR REPLACE).

        finished=True 时自动写 finished_at; phase 通常在 status='running' 时
        设当前阶段 (B6 SSE 可按 phase 切推送), 终态时设为 'done'/'failed'.
        """
        conn = get_connection()
        finished_at = _now_localtime() if finished else None
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO skill_runs(
                    run_id, ticket_id, skill_id, status, phase,
                    inputs, result, metrics, error, created_at, finished_at
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    COALESCE(
                        (SELECT created_at FROM skill_runs WHERE run_id = ?),
                        ?
                    ),
                    COALESCE(?, (SELECT finished_at FROM skill_runs WHERE run_id = ?))
                )
                """,
                (
                    run_id,
                    ticket_id,
                    skill_id,
                    status,
                    phase,
                    _json_dump(inputs) if inputs is not None else None,
                    _json_dump(result) if result is not None else None,
                    _json_dump(metrics) if metrics is not None else None,
                    error,
                    run_id,            # SELECT created_at 的占位 (主键)
                    _now_localtime(),  # 新 created_at
                    finished_at,       # 新 finished_at (若 None, 取已存)
                    run_id,            # SELECT finished_at 的占位 (主键)
                ),
            )
        except sqlite3.Error as e:
            logger.error(
                "skill_runs insert failed",
                extra={"trace_id": "", "run_id": run_id, "error": str(e)},
            )
            raise InternalException(f"skill_runs insert failed: {e}") from e

    def mark_finished(
        self,
        run_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """终态收尾 — UPDATE finished_at + status/result/metrics/error."""
        conn = get_connection()
        try:
            conn.execute(
                """
                UPDATE skill_runs
                SET status      = ?,
                    phase       = 'done',
                    result      = COALESCE(?, result),
                    metrics     = COALESCE(?, metrics),
                    error       = ?,
                    finished_at = COALESCE(finished_at, ?)
                WHERE run_id = ?
                """,
                (
                    status,
                    _json_dump(result) if result is not None else None,
                    _json_dump(metrics) if metrics is not None else None,
                    error,
                    _now_localtime(),
                    run_id,
                ),
            )
        except sqlite3.Error as e:
            logger.error(
                "skill_runs mark_finished failed",
                extra={"trace_id": "", "run_id": run_id, "error": str(e)},
            )
            raise InternalException(f"skill_runs mark_finished failed: {e}") from e

    def update_phase(self, run_id: str, phase: str) -> None:
        """阶段切换 — B6 SSE 推送按 phase 切; status 保持 running."""
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE skill_runs SET phase = ? WHERE run_id = ?",
                (phase, run_id),
            )
        except sqlite3.Error as e:
            logger.error(
                "skill_runs update_phase failed",
                extra={"trace_id": "", "run_id": run_id, "error": str(e)},
            )
            raise InternalException(f"skill_runs update_phase failed: {e}") from e

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def get(self, run_id: str) -> dict[str, Any] | None:
        """按 run_id 取一行 (反序列化 JSON 字段); 缺失返回 None."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM skill_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        except sqlite3.Error as e:
            logger.error(
                "skill_runs get failed",
                extra={"trace_id": "", "run_id": run_id, "error": str(e)},
            )
            raise InternalException(f"skill_runs get failed: {e}") from e
        if row is None:
            return None
        return _row_to_dict(row)

    def list_for_skill(self, skill_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """按 skill 维度取最近 runs — RunHistory 直接消费."""
        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT * FROM skill_runs
                WHERE skill_id = ?
                ORDER BY created_at DESC, run_id DESC
                LIMIT ?
                """,
                (skill_id, limit),
            ).fetchall()
        except sqlite3.Error as e:
            logger.error(
                "skill_runs list_for_skill failed",
                extra={"trace_id": "", "skill_id": skill_id, "error": str(e)},
            )
            raise InternalException(f"skill_runs list_for_skill failed: {e}") from e
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """反序列化 JSON 字段; 保持行结构扁平."""
    out = dict(row)
    for k in ("inputs", "result", "metrics"):
        raw = out.get(k)
        if isinstance(raw, str) and raw:
            try:
                out[k] = json.loads(raw)
            except (TypeError, ValueError):
                # 解析失败留原样, 调用方按字符串处理
                pass
    return out


__all__ = ["SkillRunRepo", "SkillRunResult"]
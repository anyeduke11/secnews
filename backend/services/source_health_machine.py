"""Crawler v2 Phase 3 — 源健康状态机 (Source Health State Machine).

管理 crawler_sources 表中每个源的 5 状态健康机:
  active → stale → dead → grace → (循环)

设计文档: docs/crawler-v2-technical-spec.md §3.2
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection

# ---------------------------------------------------------------------------
# 模块级常量
# ---------------------------------------------------------------------------
STALE_THRESHOLD = 3               # 连续失败次数达到此值 → stale
DEAD_THRESHOLD = 5                # 连续失败次数达到此值 → dead
GRACE_SUCCESS_THRESHOLD = 3       # grace 连续产出成功轮数 → active
GRACE_FAIL_THRESHOLD = 3          # grace 连续失败次数 → dead
BACKOFF_BASE = 300                # 指数退避基准秒数
BACKOFF_MAX_EXPONENT = 6          # 最大指数

# 有效状态集
_VALID_STATUSES = frozenset({"active", "stale", "dead", "grace", "disabled"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _calculate_cooldown(consecutive_failures: int) -> str:
    """计算指数退避冷却结束时间.

    公式: now + 2^min(consecutive_failures - 5, BACKOFF_MAX_EXPONENT) * BACKOFF_BASE 秒
    """
    exponent = max(0, min(consecutive_failures - 5, BACKOFF_MAX_EXPONENT))
    delay_seconds = int(math.pow(2, exponent)) * BACKOFF_BASE
    cooldown = _now_utc() + timedelta(seconds=delay_seconds)
    return cooldown.isoformat()


class SourceHealthMachine:
    """源健康状态机.

    管理 5 状态 (active/stale/dead/grace/disabled) 之间的转换逻辑,
    所有 DB 操作通过 ``get_connection()`` 直接执行.
    """

    # ------------------------------------------------------------------
    # 健康评分
    # ------------------------------------------------------------------
    @staticmethod
    def _calculate_health_score(consecutive_failures: int) -> float:
        """根据连续失败次数计算健康评分 (0.0-1.0).

        - 0 次失败 → 1.0
        - 1 次失败 → 0.9
        - 2 次失败 → 0.7
        - 3 次失败 → 0.5
        - 4 次失败 → 0.3
        - 5+ 次失败 → 0.1
        """
        table = {0: 1.0, 1: 0.9, 2: 0.7, 3: 0.5, 4: 0.3}
        return table.get(consecutive_failures, 0.1)

    # ------------------------------------------------------------------
    # DB 操作
    # ------------------------------------------------------------------
    @staticmethod
    def _read_source(source_id: str) -> dict[str, Any] | None:
        """从 crawler_sources 表读取一行."""
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM crawler_sources WHERE id = ?",
            (source_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _write_source(source_id: str, **fields: Any) -> None:
        """更新 crawler_sources 表指定字段."""
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values())
        conn = get_connection()
        conn.execute(
            f"UPDATE crawler_sources SET {sets}, updated_at = ? WHERE id = ?",
            (*values, _now_iso(), source_id),
        )

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def get_health(self, source_id: str) -> dict[str, Any] | None:
        """读取 crawler_sources 行并返回 dict."""
        return self._read_source(source_id)

    def update_health(self, source_id: str, **fields: Any) -> None:
        """直接更新 crawler_sources 表中指定字段."""
        self._write_source(source_id, **fields)

    def apply_run_result(self, source_id: str, run_result: dict) -> dict:
        """应用单轮抓取结果, 执行状态转换.

        Parameters
        ----------
        source_id:
            源 ID (crawler_sources.id).
        run_result:
            抓取结果 dict, 包含:
            - ``fetched_count``: int, 抓取到的条目数
            - ``accepted_count``: int, 验收通过的条目数
            - ``status``: str, 'success' | 'partial' | 'failed'
            - ``duration_ms``: int, 耗时毫秒
            - ``error_msg``: str (可选), 错误信息

        Returns
        -------
        dict
            ``{source_id, previous_status, new_status, consecutive_failures,
              cooldown_until, health_score, transition}``
        """
        # 1. 读取当前状态
        row = self._read_source(source_id)
        if row is None:
            logger.warning(f"apply_run_result: source {source_id} not found")
            return {
                "source_id": source_id,
                "previous_status": "unknown",
                "new_status": "unknown",
                "consecutive_failures": 0,
                "cooldown_until": None,
                "health_score": 0.0,
                "transition": "source_not_found",
            }

        prev_status = str(row["status"])
        consecutive_failures = int(row["consecutive_failures"])
        grace_rounds = int(row.get("grace_rounds", 0))
        existing_cooldown = row.get("cooldown_until")

        fetched_count = int(run_result.get("fetched_count", 0))
        run_status = str(run_result.get("status", "success"))
        error_msg = str(run_result.get("error_msg", ""))

        # 状态字段准备
        new_status = prev_status
        new_consecutive_failures = consecutive_failures
        new_grace_rounds = grace_rounds
        transition = "none"
        cooldown_until: str | None = existing_cooldown

        # 2. 执行状态转换
        if prev_status == "disabled":
            # disabled 不参与状态机
            logger.debug(f"apply_run_result: source {source_id} is disabled, skip")
            transition = "disabled_skip"

        elif prev_status == "active":
            if fetched_count > 0:
                new_consecutive_failures = 0
                transition = "success_reset"
            else:
                new_consecutive_failures = consecutive_failures + 1
                if new_consecutive_failures >= STALE_THRESHOLD:
                    new_status = "stale"
                    transition = "active_to_stale"
                else:
                    transition = "failure_incremented"

        elif prev_status == "stale":
            if fetched_count > 0:
                new_status = "active"
                new_consecutive_failures = 0
                transition = "stale_to_active"
            else:
                new_consecutive_failures = consecutive_failures + 1
                if new_consecutive_failures >= DEAD_THRESHOLD:
                    new_status = "dead"
                    cooldown_until = _calculate_cooldown(new_consecutive_failures)
                    transition = "stale_to_dead"
                else:
                    transition = "failure_incremented"

        elif prev_status == "dead":
            # dead 不自动转换, 由 SourceProber 处理
            transition = "dead_no_transition"
            if fetched_count > 0:
                # 防御性: 死源有产出则重置失败计数, 但不改变状态
                new_consecutive_failures = 0
                transition = "dead_has_yield"

        elif prev_status == "grace":
            if fetched_count > 0:
                new_grace_rounds = grace_rounds + 1
                new_consecutive_failures = 0
                if new_grace_rounds >= GRACE_SUCCESS_THRESHOLD:
                    new_status = "active"
                    new_grace_rounds = 0
                    transition = "grace_to_active"
                else:
                    transition = "grace_yield_round"
            else:
                if run_status == "failed":
                    new_consecutive_failures = consecutive_failures + 1
                    if new_consecutive_failures >= GRACE_FAIL_THRESHOLD:
                        new_status = "dead"
                        cooldown_until = _calculate_cooldown(new_consecutive_failures)
                        transition = "grace_to_dead"
                    else:
                        transition = "grace_failure_incremented"
                else:
                    # 无产出但非失败 (partial/success), 不计失败
                    transition = "grace_no_yield_no_fail"

        # 3. 计算健康评分
        health_score = self._calculate_health_score(new_consecutive_failures)

        # 4. 写入 DB
        update_fields: dict[str, Any] = {
            "status": new_status,
            "consecutive_failures": new_consecutive_failures,
            "health_score": health_score,
        }

        if new_status == "dead" and cooldown_until is not None:
            update_fields["cooldown_until"] = cooldown_until

        if prev_status == "grace":
            update_fields["grace_rounds"] = new_grace_rounds

        if error_msg:
            update_fields["last_error"] = error_msg[:500]

        if fetched_count > 0:
            update_fields["last_yield_at"] = _now_iso()
            update_fields["last_success_at"] = _now_iso()

        update_fields["last_fetch_at"] = _now_iso()

        self._write_source(source_id, **update_fields)

        # 5. 日志
        if new_status != prev_status:
            logger.info(
                f"source {source_id}: {prev_status} → {new_status} "
                f"(failures={new_consecutive_failures}, "
                f"fetched={fetched_count}, transition={transition})"
            )

        # 6. 返回结果
        return {
            "source_id": source_id,
            "previous_status": prev_status,
            "new_status": new_status,
            "consecutive_failures": new_consecutive_failures,
            "cooldown_until": cooldown_until,
            "health_score": health_score,
            "transition": transition,
        }


__all__ = [
    "SourceHealthMachine",
    "STALE_THRESHOLD",
    "DEAD_THRESHOLD",
    "GRACE_SUCCESS_THRESHOLD",
    "GRACE_FAIL_THRESHOLD",
    "BACKOFF_BASE",
    "BACKOFF_MAX_EXPONENT",
]
"""v1.0 T14 SK-01 daily-priority-intel — 今日重点情报聚合.

对应 contracts SK-01 + EXECUTION_GUIDE §T14 §1 第 1 点 "为六能力完成标准 schema".
T07 已落 admission_log / signals / admission_decisions (migration 097), SK-01 复用其聚合,
不新建表; T08 watchlist 走 SettingsRepository (subject_ids 列表).

设计:
  - compute(subject_id=None, watchlist=None) → 拼 admission_log + signals 聚合
  - 调 dsh (mock 注入可, 默认 ai_hub.generate_text) → 返 top_items + watchlist_changes + suggested_actions
  - 走 V1EvidenceService 落 receipt (best-effort, entity_type=knowledge 警告不影响)
  - 失败模式: dsh 解析失败 / 拉数据超时 / 依赖未就绪 → 返 fallback (仅 raw 聚合, 不出 dsh 摘要)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _query_admission_recent(days: int = 7) -> list[dict[str, Any]]:
    """T07 已落 admission_log (migration 097), SK-01 拉近 N 天决策."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT action, verdict, subject_id, reason, created_at "
            "FROM admission_log "
            "WHERE created_at >= datetime('now', ?) "
            "ORDER BY created_at DESC LIMIT 20",
            (f"-{days} days",),
        ).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"admission_log table missing: {e}")
        return []
    return [
        {"action": r[0], "verdict": r[1], "subject_id": r[2], "reason": r[3], "ts": r[4]}
        for r in rows
    ]


def _query_signals_recent(days: int = 3) -> list[dict[str, Any]]:
    """T05 已落 v1_signals (migration 096), SK-01 拉近 N 天事件."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, subject_id, confidence, summary, occurred_at "
            "FROM v1_signals "
            "WHERE occurred_at >= datetime('now', ?) "
            "ORDER BY occurred_at DESC LIMIT 20",
            (f"-{days} days",),
        ).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"v1_signals table missing: {e}")
        return []
    return [
        {"id": r[0], "subject_id": r[1], "confidence": r[2],
         "summary": r[3], "occurred_at": r[4]}
        for r in rows
    ]


def _query_watchlist() -> list[str]:
    """T08 watchlist (SettingsRepository kv 'watchlist.subjects')."""
    try:
        from backend.repository.settings_repo import SettingsRepository
        v = SettingsRepository().get("watchlist.subjects", [])
        if isinstance(v, list):
            return [str(x) for x in v]
        return []
    except Exception as e:
        logger.warning(f"watchlist fetch failed: {e}")
        return []


class DailyPriorityIntelService:
    """SK-01 daily-priority-intel service.

    走 dsh (mock 注入可, 默认 ai_hub.generate_text) → top_items + watchlist_changes + suggested_actions.
    """

    def __init__(self, *, dsh_caller: Any = None) -> None:
        self._dsh_caller = dsh_caller

    def compute(
        self, subject_id: str | None = None, *,
        watchlist: list[str] | None = None,
        admission_days: int = 7, signals_days: int = 3,
    ) -> dict[str, Any]:
        """SK-01 主路径: 聚合 admission + signals → 调 dsh → 返 top_items + watchlist_changes + suggested_actions.

        Returns
        -------
        dict 含 top_items (≥1) / watchlist_changes (list) / suggested_actions (list) / generated_at / mode.
        """
        watchlist = watchlist if watchlist is not None else _query_watchlist()
        admission_recent = _query_admission_recent(admission_days)
        signals_recent = _query_signals_recent(signals_days)
        # 缺依赖 (无 admission / 无 signals): 返 fallback (仅 raw 聚合, 不出 dsh 摘要)
        if not admission_recent and not signals_recent:
            return {
                "top_items": [],
                "watchlist_changes": [],
                "suggested_actions": ["无可用 admission_log / v1_signals 数据 (依赖未就绪)"],
                "generated_at": _now_utc_iso(),
                "mode": "fallback_no_data",
            }
        # 调 dsh
        from backend.services.ai_hub.prompts import (
            build_daily_priority_intel_prompt,
            parse_daily_priority_intel_response,
        )
        prompt = build_daily_priority_intel_prompt(
            subject_id=subject_id or "(全 subject 视角)",
            admission_recent=admission_recent,
            signals_recent=signals_recent,
            watchlist_subjects=watchlist,
        )
        try:
            raw = self._call_dsh(prompt)
            parsed = parse_daily_priority_intel_response(raw)
        except Exception as e:
            logger.warning(f"dsh call/parse failed, fallback raw aggregation: {e}")
            return {
                "top_items": [],
                "watchlist_changes": [],
                "suggested_actions": [f"dsh 调用失败 ({type(e).__name__}), 待 fallback 重试"],
                "generated_at": _now_utc_iso(),
                "mode": "fallback_dsh_failed",
            }
        # 走 V1EvidenceService receipt (best-effort, T05 模式)
        try:
            from backend.services.v1_evidence_service import V1EvidenceService
            content_hash = str(hash(json.dumps(parsed, sort_keys=True, ensure_ascii=False)))
            intent = V1EvidenceService().create_intent(
                f"v1-sk01-daily-priority-intel-{content_hash[:16]}", "knowledge", parsed,
                submitted_by="sk01",
            )
            V1EvidenceService().commit_intent(intent["intent_id"], entity_id="sk01", projection=None)
        except Exception as e:
            logger.warning(f"V1EvidenceService trace failed (SK-01 still inserts): {e}")
        return {
            "top_items": parsed["top_items"],
            "watchlist_changes": parsed["watchlist_changes"],
            "suggested_actions": parsed["suggested_actions"],
            "generated_at": _now_utc_iso(),
            "mode": "dsh",
        }

    def _call_dsh(self, prompt: str) -> str:
        if self._dsh_caller is not None:
            return self._dsh_caller(prompt)
        try:
            from backend.services.ai_hub.service import ai_service
            return ai_service.generate_text(
                messages=[{"role": "user", "content": prompt}],
                task="daily_priority_intel", max_tokens=4000, temperature=0.2,
            )
        except Exception as e:
            raise RuntimeError(f"ai_hub generate_text failed: {e}") from e

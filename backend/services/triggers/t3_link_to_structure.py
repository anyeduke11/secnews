"""T3 trigger — advance ``kl:link`` items to ``kl:structure``.

Phase 12 — third hop in the KL state machine.

What T3 does
------------
1. Find ``knowledge_items`` whose ``lifecycle`` is ``kl:link``.
2. Count links from ``knowledge_links`` table where ``from_item_id = item.id``.
3. Links ≥ 3: normal advance; < 3: also advance but mark ``low_link``.
4. Generate summary: extract first 200 characters from ``content`` field.
5. Update ``lifecycle = 'kl:structure'``.

Failure handling mirrors :class:`T1Trigger` and is funnelled through
:class:`RetryPolicy`.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from backend.metrics.kl_metrics import kl_metrics
from backend.repository.db import get_connection
from backend.services.ai_hub import llm_service
from backend.services.kl_state_machine import (
    LIFECYCLE_LINK,
    LIFECYCLE_STRUCTURE,
    can_transition,
)
from backend.services.retry_policy import RetryPolicy

logger = logging.getLogger("hotspot.trigger.t3")

BATCH_SIZE = 50
TRIGGER_NAME = "t3"
FROM_STAGE = LIFECYCLE_LINK
TO_STAGE = LIFECYCLE_STRUCTURE
LOW_LINK_THRESHOLD = 3


class T3Trigger:
    """Advance ``kl:link`` items to ``kl:structure`` with link-count check.

    Parameters
    ----------
    metrics:
        Counter / gauge / histogram store.  Defaults to the shared
        :data:`backend.metrics.kl_metrics.kl_metrics` singleton.
    retry_policy:
        Business-layer retry + dead-letter writer.  Defaults to a
        :class:`RetryPolicy` that targets the
        :class:`KLDeadLetterRepository` singleton.
    """

    def __init__(
        self,
        metrics: Any = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.metrics = metrics if metrics is not None else kl_metrics
        self.retry = retry_policy or RetryPolicy(metrics=self.metrics)

    # ── Public entry point ────────────────────────────────────────

    def run_once(self) -> dict[str, int]:
        """Run one T3 cycle. Returns a stats dict."""
        t0 = time.monotonic()
        self.metrics.inc("t3_triggered")

        candidates = self._fetch_candidates()
        advanced = 0
        low_link = 0
        failed = 0

        for item in candidates:
            item_id = item["id"]
            try:
                link_count = self._count_links(item_id)
                if link_count < LOW_LINK_THRESHOLD:
                    low_link += 1

                # 状态机守卫: can_transition 返回 bool 且不抛异常
                # (见 backend/services/kl_state_machine.py:98), 原先调用后丢弃返回值
                # 等于任何 lifecycle 都可被强推到 kl:structure。
                if not can_transition(item["lifecycle"], LIFECYCLE_STRUCTURE):
                    failed += 1
                    self.metrics.inc("t3_failed")
                    logger.warning(
                        "T3: illegal transition %s → %s for %s",
                        item["lifecycle"], LIFECYCLE_STRUCTURE, item_id,
                    )
                    continue
                self._update_lifecycle(item_id, LIFECYCLE_STRUCTURE)
                advanced += 1
                self.metrics.inc("t3_succeeded")
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                self.metrics.inc("t3_failed")
                self.retry.handle_failure(TRIGGER_NAME, item_id, exc)

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        self.metrics.observe("t3_latency_ms", elapsed_ms)

        report = {
            "candidates": len(candidates),
            "advanced": advanced,
            "low_link": low_link,
            "failed": failed,
        }
        logger.info(f"T3 cycle: {report} elapsed_ms={elapsed_ms:.1f}")
        return report

    # ── Read helpers ──────────────────────────────────────────────

    @staticmethod
    def _fetch_candidates() -> list[dict[str, Any]]:
        """Return ``kl:link`` items (no time limit on T3).

        注意列白名单: ``knowledge_items`` 无 ``content`` 列 (真实 schema 24 列 +
        全部迁移均无), 带上会抛 ``no such column: content`` 并使整个 job 每轮
        崩溃 —— 实测日志中该错误连续出现 167 次, kl:link→kl:structure 长期全断。
        t4 已按同样方式修过 (见 ``t4_structure_to_publish.py`` P1-2 注释)。
        """
        sql = (
            "SELECT id, title, lifecycle, "
            "ingested_at, updated_at "
            "FROM knowledge_items "
            "WHERE lifecycle = ? "
            "ORDER BY ingested_at ASC "
            "LIMIT ?"
        )
        conn = get_connection()
        rows = conn.execute(sql, (LIFECYCLE_LINK, BATCH_SIZE)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _count_links(item_id: str) -> int:
        """Return the number of knowledge_links rows pointing from this item."""
        conn = get_connection()
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM knowledge_links WHERE from_item_id = ?",
            (item_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def _summarize_with_llm(self, item: dict[str, Any]) -> str:
        """Try LLM summarization first, fall back to text truncation."""
        content = item.get("content") or item.get("title") or ""
        if content.strip():
            import asyncio
            try:
                summary = asyncio.run(llm_service.summarize([content]))
                if summary:
                    self.metrics.observe("t3_llm_summary_ms", 0)
                    return summary
            except Exception:
                pass
        return self._generate_summary(item)

    @staticmethod
    def _generate_summary(item: dict[str, Any]) -> str:
        """Extract the first 200 characters of the item's content as summary."""
        content = item.get("content") or ""
        return content[:200]

    @staticmethod
    def _update_lifecycle(item_id: str, new_stage: str) -> None:
        conn = get_connection()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE knowledge_items "
            "SET lifecycle = ?, updated_at = ? "
            "WHERE id = ?",
            (new_stage, now_iso, item_id),
        )


__all__ = [
    "BATCH_SIZE",
    "FROM_STAGE",
    "LOW_LINK_THRESHOLD",
    "TO_STAGE",
    "TRIGGER_NAME",
    "T3Trigger",
]
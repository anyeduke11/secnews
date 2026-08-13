"""T4 trigger — advance ``kl:structure`` items to ``kl:publish``.

Phase 12 — fourth hop in the KL state machine.

What T4 does
------------
1. Find ``knowledge_items`` whose ``lifecycle`` is ``kl:structure``
   (ordered by ``ingested_at`` ASC, up to :data:`BATCH_SIZE`).
2. Score check: query the latest ``ai_scores.score``; must be ≥
   :data:`MIN_SCORE` (8.0).  Items with no score row get a 5.0
   fallback and are skipped.
3. Stability window: ``updated_at`` must be at least
   :data:`STABLE_WINDOW_HOURS` (24) in the past — prevents publishing
   content that was just structured.
4. .md write: call ``knowledge_sync.write_item_to_md()`` to persist
   the item as ``knowledge/items/{id}.md``.
5. Update ``lifecycle = 'kl:publish'`` and bump ``updated_at``.

Failure handling
----------------
Any exception during per-item work is funnelled through the
:class:`RetryPolicy` injected at construction time, which writes a
``kl_dead_letters`` row after 3 attempts and increments the
``t4_dead_letter`` counter.

Metrics
-------
Emits the following counter names on the shared :data:`kl_metrics`
singleton:

- ``t4_triggered`` (once per :meth:`run_once`)
- ``t4_succeeded`` (per item advanced)
- ``t4_failed`` (per item that raised)
- ``t4_dead_letter`` (via RetryPolicy on 3rd failure)

And one histogram sample:

- ``t4_latency_ms`` (total wall time of :meth:`run_once`)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.metrics.kl_metrics import kl_metrics
from backend.repository.db import get_connection
from backend.services.kl_state_machine import (
    LIFECYCLE_STRUCTURE,
    LIFECYCLE_PUBLISH,
    can_transition,
)
from backend.services.retry_policy import RetryPolicy

logger = logging.getLogger("hotspot.trigger.t4")

# Public tunables
BATCH_SIZE = 50
TRIGGER_NAME = "t4"
FROM_STAGE = LIFECYCLE_STRUCTURE
TO_STAGE = LIFECYCLE_PUBLISH
STABLE_WINDOW_HOURS = 24
MIN_SCORE = 8.0
DEFAULT_SCORE = 5.0  # fallback when ai_scores is empty


class T4Trigger:
    """Advance ``kl:structure`` items to ``kl:publish`` with score + stability gates.

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
        retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        self.metrics = metrics if metrics is not None else kl_metrics
        self.retry = retry_policy or RetryPolicy(metrics=self.metrics)

    # ── Public entry point ────────────────────────────────────────

    def run_once(self) -> Dict[str, int]:
        """Run one T4 cycle. Returns a stats dict.

        Returns
        -------
        dict
            Mapping with keys ``candidates``, ``advanced``,
            ``skipped_low_score``, ``skipped_unstable``, ``failed``.
        """
        t0 = time.monotonic()
        self.metrics.inc("t4_triggered")

        candidates = self._fetch_candidates()

        advanced = 0
        skipped_low_score = 0
        skipped_unstable = 0
        failed = 0

        for item in candidates:
            item_id = item["id"]
            try:
                score = self._get_latest_score(item_id)
                if score < MIN_SCORE:
                    skipped_low_score += 1
                    continue

                if not self._is_stable(item):
                    skipped_unstable += 1
                    continue

                # Validate transition; raises on stale / illegal data.
                can_transition(item["lifecycle"], LIFECYCLE_PUBLISH)
                self._write_to_md(item)
                self._update_lifecycle(item_id, LIFECYCLE_PUBLISH)
                advanced += 1
                self.metrics.inc("t4_succeeded")
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                self.metrics.inc("t4_failed")
                self.retry.handle_failure(TRIGGER_NAME, item_id, exc)

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        self.metrics.observe("t4_latency_ms", elapsed_ms)

        report = {
            "candidates": len(candidates),
            "advanced": advanced,
            "skipped_low_score": skipped_low_score,
            "skipped_unstable": skipped_unstable,
            "failed": failed,
        }
        logger.info(f"T4 cycle: {report} elapsed_ms={elapsed_ms:.1f}")
        return report

    # ── Read helpers ──────────────────────────────────────────────

    def _fetch_candidates(self) -> List[Dict[str, Any]]:
        """Return ``kl:structure`` items ordered by ingestion time."""
        sql = (
            "SELECT id, title, content, lifecycle, ingested_at, updated_at "
            "FROM knowledge_items "
            "WHERE lifecycle = ? "
            "ORDER BY ingested_at ASC "
            "LIMIT ?"
        )
        conn = get_connection()
        rows = conn.execute(sql, (LIFECYCLE_STRUCTURE, BATCH_SIZE)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _get_latest_score(item_id: str) -> float:
        """Read the most recent ``ai_scores.score`` for the item, else default."""
        conn = get_connection()
        row = conn.execute(
            "SELECT score FROM ai_scores "
            "WHERE hotspot_id = ? "
            "ORDER BY scored_at DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        if row is None:
            return DEFAULT_SCORE
        try:
            return float(row["score"])
        except (TypeError, ValueError):
            return DEFAULT_SCORE

    @staticmethod
    def _is_stable(item: Dict[str, Any]) -> bool:
        """Return True if the item has been stable for the full window.

        Parses ``item["updated_at"]`` as an ISO-8601 datetime and checks
        that it is at least :data:`STABLE_WINDOW_HOURS` in the past.
        """
        raw = item.get("updated_at")
        if not raw:
            return False
        try:
            updated = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            logger.warning(f"unparseable updated_at for item {item.get('id')}: {raw!r}")
            return False
        # If the datetime is naive, assume UTC.
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STABLE_WINDOW_HOURS)
        return updated < cutoff

    # ── Write helpers ─────────────────────────────────────────────

    @staticmethod
    def _write_to_md(item: Dict[str, Any]) -> None:
        """Write the item to ``knowledge/items/{id}.md``."""
        from backend.services.knowledge_sync import write_item_to_md

        write_item_to_md(item)

    @staticmethod
    def _update_lifecycle(item_id: str, new_stage: str) -> None:
        """Write ``new_stage`` into ``knowledge_items.lifecycle``."""
        conn = get_connection()
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE knowledge_items "
            "SET lifecycle = ?, updated_at = ? "
            "WHERE id = ?",
            (new_stage, now_iso, item_id),
        )


__all__ = [
    "T4Trigger",
    "BATCH_SIZE",
    "TRIGGER_NAME",
    "FROM_STAGE",
    "TO_STAGE",
    "STABLE_WINDOW_HOURS",
    "MIN_SCORE",
    "DEFAULT_SCORE",
]
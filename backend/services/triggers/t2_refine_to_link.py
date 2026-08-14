"""T2 trigger — advance ``kl:refine`` items to ``kl:link``.

Phase 10 — second hop in the KL state machine.

What T2 does
------------
1. Find ``knowledge_items`` whose ``lifecycle`` is in the refine-like
   set (``kl:refine`` + legacy ``amplify:tagged`` for unfinished 046).
2. Extract the item's concept list (from the ``concepts`` JSON column
   or the ``tags`` column as a fallback).
3. Look up to 5 related items that share at least one concept, via
   ``knowledge_items`` joined on the JSON-encoded concept slugs.
4. Write one ``knowledge_links`` row per related item
   (``link_type='similar'``, ``confidence=0.7``, ``created_by='trigger'``).
5. Update ``lifecycle = 'kl:link'`` even when no related item is found
   (``low_link`` is counted but does not block promotion — see spec §4.3).

Failure handling mirrors :class:`T1Trigger` and is funnelled through
:class:`RetryPolicy`.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from backend.metrics.kl_metrics import kl_metrics
from backend.repository.db import get_connection
from backend.services.kl_state_machine import (
    LEGACY_REFINE_LIKE,
    LIFECYCLE_LINK,
    LIFECYCLE_REFINE,
    can_transition,
)
from backend.services.retry_policy import RetryPolicy

logger = logging.getLogger("hotspot.trigger.t2")

BATCH_SIZE = 50
TRIGGER_NAME = "t2"
FROM_STAGE = LIFECYCLE_REFINE
TO_STAGE = LIFECYCLE_LINK
LINK_CONFIDENCE = 0.7
MAX_RELATED = 5

# Refine-like stages T2 is allowed to pick up.  We accept the legacy
# ``amplify:tagged`` value as refine-equivalent until migration 046 runs.
_REFINE_LIKE_STAGES = (LIFECYCLE_REFINE, LEGACY_REFINE_LIKE)


class T2Trigger:
    """Advance ``kl:refine`` items to ``kl:link`` with concept matching.

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
        """Run one T2 cycle. Returns a stats dict."""
        t0 = time.monotonic()
        self.metrics.inc("t2_triggered")

        candidates = self._fetch_candidates()
        advanced = 0
        low_link = 0
        failed = 0

        for item in candidates:
            item_id = item["id"]
            try:
                if not self._is_refine_like(item["lifecycle"]):
                    continue

                concepts = self._extract_concepts(item)
                related_ids: list[str] = []
                if concepts:
                    related_ids = self._find_related_items(item_id, concepts)

                if related_ids:
                    self._write_links(item_id, related_ids)
                else:
                    low_link += 1

                can_transition(item["lifecycle"], LIFECYCLE_LINK)
                self._update_lifecycle(item_id, LIFECYCLE_LINK)
                advanced += 1
                self.metrics.inc("t2_succeeded")
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                self.metrics.inc("t2_failed")
                self.retry.handle_failure(TRIGGER_NAME, item_id, exc)

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        self.metrics.observe("t2_latency_ms", elapsed_ms)

        report = {
            "candidates": len(candidates),
            "advanced": advanced,
            "low_link": low_link,
            "failed": failed,
        }
        logger.info(f"T2 cycle: {report} elapsed_ms={elapsed_ms:.1f}")
        return report

    # ── Read helpers ──────────────────────────────────────────────

    def _fetch_candidates(self) -> list[dict[str, Any]]:
        """Return refine-like items (no time debounce on T2)."""
        placeholders = ",".join("?" for _ in _REFINE_LIKE_STAGES)
        sql = (
            f"SELECT id, title, source_url, concepts, tags, lifecycle, "
            f"ingested_at, updated_at "
            f"FROM knowledge_items "
            f"WHERE lifecycle IN ({placeholders}) "
            f"ORDER BY ingested_at ASC "
            f"LIMIT ?"
        )
        conn = get_connection()
        rows = conn.execute(
            sql, (*_REFINE_LIKE_STAGES, BATCH_SIZE)
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _is_refine_like(lifecycle: str) -> bool:
        return lifecycle in _REFINE_LIKE_STAGES

    @staticmethod
    def _extract_concepts(item: dict[str, Any]) -> list[str]:
        """Return the concept slug list for an item.

        Reads the ``concepts`` JSON column first; falls back to ``tags``
        (also a JSON list) when ``concepts`` is missing or empty.
        Returns an empty list when both are unusable.
        """
        for key in ("concepts", "tags"):
            raw = item.get(key)
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list) and parsed:
                    return [str(c) for c in parsed if str(c).strip()]
            except (TypeError, ValueError):
                continue
        return []

    @staticmethod
    def _find_related_items(
        item_id: str, concepts: list[str]
    ) -> list[str]:
        """Return up to :data:`MAX_RELATED` other item ids sharing a concept.

        Strategy
        --------
        We look at all items in refine-like OR link-like stages so that
        a previously processed item (already advanced to ``kl:link``)
        is still discoverable as a related peer. This is what makes
        the trigger produce BOTH directions of a link (src→dst and
        dst→src) within a single cycle.

        ``knowledge_items.concepts`` is a JSON string column, so we
        load a small batch and check overlap in Python. This is O(n)
        on at most :data:`BATCH_SIZE` rows — JSON-SQL matching is
        brittle across SQLite versions and not worth the complexity
        for the Phase 10 scale.
        """
        if not concepts:
            return []
        concepts_set: set[str] = {c.strip() for c in concepts if c and c.strip()}
        if not concepts_set:
            return []
        # Look in BOTH refine-like and link-like stages. This makes the
        # link graph symmetric within a single cycle: after we advance
        # "src" → kl:link, "dst" can still see it as a related peer.
        # We deliberately exclude the item itself to prevent self-links.
        all_peer_stages = (
            LIFECYCLE_REFINE, LEGACY_REFINE_LIKE, LIFECYCLE_LINK,
        )
        placeholders = ",".join("?" for _ in all_peer_stages)
        sql = (
            f"SELECT id, concepts, tags FROM knowledge_items "
            f"WHERE lifecycle IN ({placeholders}) AND id != ? "
            f"LIMIT 500"
        )
        conn = get_connection()
        rows = conn.execute(
            sql, (*all_peer_stages, item_id)
        ).fetchall()
        related: list[str] = []
        seen: set[str] = set()
        for row in rows:
            rid = row["id"]
            if rid in seen:
                continue
            for key in ("concepts", "tags"):
                raw = row[key]
                if not raw:
                    continue
                try:
                    parsed = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(parsed, list):
                    continue
                other = {str(c).strip() for c in parsed if str(c).strip()}
                if other & concepts_set:
                    related.append(rid)
                    seen.add(rid)
                    break
            if len(related) >= MAX_RELATED:
                break
        return related

    @staticmethod
    def _write_links(from_id: str, related_ids: list[str]) -> None:
        """Insert one ``knowledge_links`` row per related id.

        ``INSERT OR IGNORE`` keeps the call idempotent — the unique
        index on ``(from_item_id, to_item_id, link_type)`` prevents
        duplicate rows on subsequent cycles.
        """
        if not related_ids:
            return
        conn = get_connection()
        for to_id in related_ids:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO knowledge_links
                        (from_item_id, to_item_id, link_type,
                         confidence, created_by)
                    VALUES (?, ?, 'similar', ?, 'trigger')
                    """,
                    (from_id, to_id, LINK_CONFIDENCE),
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    f"link insert failed: {from_id} -> {to_id}: {exc}"
                )

    @staticmethod
    def _update_lifecycle(item_id: str, new_stage: str) -> None:
        conn = get_connection()
        from datetime import datetime, timezone
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
    "LINK_CONFIDENCE",
    "MAX_RELATED",
    "TO_STAGE",
    "TRIGGER_NAME",
    "T2Trigger",
]

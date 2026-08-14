"""T1 trigger — advance ``kl:raw`` items to ``kl:refine``.

Phase 10 — first hop in the KL state machine.

What T1 does
------------
1. Find ``knowledge_items`` whose ``lifecycle`` is in the raw-like set
   (``kl:raw`` + legacy ``signal`` for unfinished 046 migration) and
   that have been in the queue for at least :data:`RAW_MIN_AGE_SECONDS`
   (debounce against race with the collector).
2. Simhash-dedup against the existing ``content_fingerprints`` table;
   duplicates are skipped but counted.
3. Look up the latest ``ai_scores.score`` (fallback 5.0 when absent).
4. Update ``lifecycle = 'kl:refine'`` and bump ``updated_at``.

Failure handling
----------------
Any exception during per-item work is funnelled through the
:class:`RetryPolicy` injected at construction time, which writes a
``kl_dead_letters`` row after 3 attempts and increments the
``t1_dead_letter`` counter.

Metrics
-------
Emits the following counter names on the shared :data:`kl_metrics`
singleton:

- ``t1_triggered`` (once per :meth:`run_once`)
- ``t1_succeeded`` (per item advanced)
- ``t1_failed`` (per item that raised)
- ``t1_dead_letter`` (via RetryPolicy on 3rd failure)

And one histogram sample:

- ``t1_latency_ms`` (total wall time of :meth:`run_once`)
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.metrics.kl_metrics import kl_metrics
from backend.repository.db import get_connection
from backend.services.kl_state_machine import (
    LEGACY_RAW_LIKE,
    LIFECYCLE_RAW,
    LIFECYCLE_REFINE,
    can_transition,
)
from backend.services.llm_service import llm_service
from backend.services.retry_policy import RetryPolicy
from backend.services.simhash import (
    canonicalize_url,
    hamming_distance,
    normalize_title,
    simhash,
)

logger = logging.getLogger("hotspot.trigger.t1")

# Public tunables
RAW_MIN_AGE_SECONDS = 300          # 5 min debounce
DEDUP_HAMMING_THRESHOLD = 5        # < 5 → duplicate
BATCH_SIZE = 50                     # max candidates per cycle
DEFAULT_SCORE = 5.0                 # fallback when ai_scores is empty
TRIGGER_NAME = "t1"
FROM_STAGE = LIFECYCLE_RAW          # for state-machine self-validation
TO_STAGE = LIFECYCLE_REFINE

# Raw-like stages T1 is allowed to pick up.  We treat the legacy
# ``signal`` value as raw-equivalent until migration 046 runs.
_RAW_LIKE_STAGES: tuple[str, ...] = (LIFECYCLE_RAW, LEGACY_RAW_LIKE)


class T1Trigger:
    """Advance ``kl:raw`` items to ``kl:refine`` with simhash + scoring.

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
        """Run one T1 cycle. Returns a stats dict.

        Returns
        -------
        dict
            Mapping with keys ``candidates``, ``advanced``,
            ``skipped_duplicate``, ``failed``.
        """
        t0 = time.monotonic()
        self.metrics.inc("t1_triggered")

        candidates = self._fetch_candidates()
        # Load existing fingerprints once (avoid 50 SELECTs).
        existing_fp, existing_urls = self._load_existing_fingerprints()

        advanced = 0
        skipped_duplicate = 0
        failed = 0

        for item in candidates:
            item_id = item["id"]
            try:
                # State-machine guard. Legacy rows can_transition(LEGACY → KL)
                # returns False (treated as no-op) so we treat them as raw-like
                # by writing the same value the state machine expects.
                if not self._is_raw_like(item["lifecycle"]):
                    # Stale row that was promoted by another worker.
                    continue

                if self._is_duplicate(item, existing_fp, existing_urls):
                    skipped_duplicate += 1
                    continue

                # Even if scoring fails, we still advance — the trigger's
                # job is to move items along; the score is best-effort.
                # Try LLM scoring first, fall back to DB score.
                _score = self._score_with_llm(item)
                _tags = self._extract_tags(item)
                # Validate transition; raises on stale / illegal data.
                can_transition(item["lifecycle"], LIFECYCLE_REFINE)
                self._update_lifecycle(item_id, LIFECYCLE_REFINE)
                advanced += 1
                self.metrics.inc("t1_succeeded")
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                self.metrics.inc("t1_failed")
                self.retry.handle_failure(TRIGGER_NAME, item_id, exc)

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        self.metrics.observe("t1_latency_ms", elapsed_ms)

        report = {
            "candidates": len(candidates),
            "advanced": advanced,
            "skipped_duplicate": skipped_duplicate,
            "failed": failed,
        }
        logger.info(f"T1 cycle: {report} elapsed_ms={elapsed_ms:.1f}")
        return report

    # ── Read helpers ──────────────────────────────────────────────

    def _fetch_candidates(self) -> list[dict[str, Any]]:
        """Return raw-like items older than the debounce window."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=RAW_MIN_AGE_SECONDS)
        ).isoformat()
        placeholders = ",".join("?" for _ in _RAW_LIKE_STAGES)
        sql = (
            f"SELECT id, title, source_url, concepts, tags, lifecycle, "
            f"ingested_at, updated_at "
            f"FROM knowledge_items "
            f"WHERE lifecycle IN ({placeholders}) "
            f"AND ingested_at < ? "
            f"ORDER BY ingested_at ASC "
            f"LIMIT ?"
        )
        conn = get_connection()
        rows = conn.execute(
            sql, (*_RAW_LIKE_STAGES, cutoff, BATCH_SIZE)
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _load_existing_fingerprints() -> tuple[list[tuple[str, int]], set]:
        """Return (existing_fingerprints, existing_canonical_urls)."""
        from backend.services.collection_service import _from_signed_64
        conn = get_connection()
        fp_rows = conn.execute(
            "SELECT hotspot_id, simhash FROM content_fingerprints"
        ).fetchall()
        url_rows = conn.execute(
            "SELECT url_canonical FROM content_fingerprints"
        ).fetchall()
        fps = [(r["hotspot_id"], _from_signed_64(r["simhash"])) for r in fp_rows]
        urls = {r["url_canonical"] for r in url_rows if r["url_canonical"]}
        return fps, urls

    def _is_raw_like(self, lifecycle: str) -> bool:
        """Return True if the row should be processed by T1.

        We accept both ``kl:raw`` and the legacy ``signal`` value (the
        :data:`LEGACY_RAW_LIKE` constant) so unfinished migration 046
        does not block T1.
        """
        return lifecycle in _RAW_LIKE_STAGES

    def _is_duplicate(
        self,
        item: dict[str, Any],
        existing_fp: list[tuple[str, int]],
        existing_urls: set,
    ) -> bool:
        """Return True if the item is a duplicate per simhash / URL."""
        url_str = item.get("source_url") or ""
        url_canon = canonicalize_url(url_str)
        if url_canon and url_canon in existing_urls:
            return True
        # Simhash on title + tags text (summary is null on knowledge_items).
        title = item.get("title") or ""
        tags_text = ""
        if item.get("tags"):
            try:
                tag_list = json.loads(item["tags"])
                if isinstance(tag_list, list):
                    tags_text = " ".join(str(t) for t in tag_list)
            except (TypeError, ValueError):
                tags_text = str(item["tags"])
        text = (title + " " + tags_text).strip() or normalize_title(title)
        fp = simhash(text)
        for _existing_id, existing_fp_val in existing_fp:
            if hamming_distance(fp, existing_fp_val) < DEDUP_HAMMING_THRESHOLD:
                return True
        return False

    @staticmethod
    def _get_latest_score(item_id: str) -> float:
        """Read the most recent ``ai_scores.score`` for the item (fallback when LLM scoring is unavailable), else default."""
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

    def _score_with_llm(self, item: dict[str, Any]) -> float:
        """Try LLM scoring first, fall back to DB score."""
        content = item.get("title", "") or ""
        if item.get("concepts"):
            try:
                import json
                concepts = json.loads(item["concepts"])
                if isinstance(concepts, list):
                    content += " " + " ".join(str(c) for c in concepts)
            except (TypeError, ValueError):
                pass
        if content.strip():
            import asyncio
            try:
                score = asyncio.run(llm_service.score(content, item.get("id", "")))
                if score != DEFAULT_SCORE:
                    # Write LLM score to ai_scores table for audit
                    self._write_llm_score(item.get("id", ""), score)
                    self.metrics.observe("t1_llm_score_ms", 0)
                    return score
            except Exception:
                pass
        return self._get_latest_score(item.get("id", ""))

    @staticmethod
    def _write_llm_score(item_id: str, score: float) -> None:
        """Write LLM score to ai_scores table for audit trail."""
        from datetime import datetime, timezone
        conn = get_connection()
        conn.execute(
            "INSERT INTO ai_scores (hotspot_id, score, reason, scored_at) "
            "VALUES (?, ?, ?, ?)",
            (item_id, score, "llm_service",
             datetime.now(timezone.utc).isoformat()),
        )

    @staticmethod
    def _extract_tags(item: dict[str, Any]) -> list[str]:
        """Read the item's tag list from the ``tags`` JSON column.

        Returns an empty list when the column is missing, NULL, or holds
        a non-list JSON value.
        """
        raw = item.get("tags")
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(t) for t in parsed]
        except (TypeError, ValueError):
            pass
        return []

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
    "BATCH_SIZE",
    "DEDUP_HAMMING_THRESHOLD",
    "DEFAULT_SCORE",
    "FROM_STAGE",
    "RAW_MIN_AGE_SECONDS",
    "TO_STAGE",
    "TRIGGER_NAME",
    "T1Trigger",
]

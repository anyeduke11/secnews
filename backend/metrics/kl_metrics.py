"""In-process metrics for the KL trigger pipeline.

Phase 10 — backs the ``GET /api/kl/metrics`` endpoint and provides a
shared counter / gauge / histogram surface for the T1/T2/T3 triggers.

We intentionally avoid ``prometheus_client`` because:

1. The dashboard reads ``/api/kl/metrics`` as plain JSON (no scraper).
2. A single-process counter avoids cross-worker aggregation problems in
   SQLite + single-worker deploys (WORKERS=1).
3. The histogram samples are kept in-process as a small ring buffer;
   the dashboard only needs avg / p50 / p99 for a few thousand samples.

Public surface
--------------
- :class:`KLMetrics` — instance API
- :data:`kl_metrics` — module-level singleton for shared use across
  triggers and the metrics API endpoint.

Counter / gauge / histogram names are stable contracts; renaming a
metric breaks the dashboard.
"""
from __future__ import annotations

import threading
from collections import deque

# ---------------------------------------------------------------------------
# Stage constants (mirrored from kl_state_machine to avoid a cycle in callers
# that want metrics without depending on the full state-machine module).
# ---------------------------------------------------------------------------
ALL_STAGES: list[str] = [
    "kl:raw", "kl:refine", "kl:link", "kl:structure", "kl:publish",
]

# Fixed counter schema — 16 counters (4 per trigger).
COUNTER_KEYS: list[str] = [
    "t1_triggered",
    "t1_succeeded",
    "t1_failed",
    "t1_dead_letter",
    "t2_triggered",
    "t2_succeeded",
    "t2_failed",
    "t2_dead_letter",
    "t3_triggered",
    "t3_succeeded",
    "t3_failed",
    "t3_dead_letter",
    "t4_triggered",
    "t4_succeeded",
    "t4_failed",
    "t4_dead_letter",
]

# Histogram keys — 4 latency series (T1 / T2 / T3 / T4 per-cycle wall time in ms).
HISTOGRAM_KEYS: list[str] = [
    "t1_latency_ms",
    "t2_latency_ms",
    "t3_latency_ms",
    "t4_latency_ms",
]

# Ring buffer size for histogram samples. 100 ≈ ~2 minutes at 60s
# T1 cadence — enough for a meaningful p50/p99 without unbounded growth.
HISTOGRAM_MAX_SAMPLES = 100


class KLMetrics:
    """Thread-safe counter / gauge / histogram store.

    Counters
    --------
    - 12 fixed keys, one increment per logical event:
      t{1,2,3}_{triggered, succeeded, failed, dead_letter}

    Gauges
    ------
    - ``by_stage_count`` — dict of stage → item count, refreshed by
      :meth:`set_stage_counts` whenever the trigger introspects the DB.

    Histograms
    ----------
    - ``t{1,2,3}_latency_ms`` — per-cycle wall time in ms.  Ring buffer of
      the most recent :data:`HISTOGRAM_MAX_SAMPLES` values.
    """

    def __init__(self) -> None:
        # Use RLock because snapshot() acquires the lock and then calls
        # histogram_summary() (which also acquires the lock). A plain
        # threading.Lock would deadlock on the recursive acquisition.
        self._lock = threading.RLock()
        self._counters: dict[str, int] = dict.fromkeys(COUNTER_KEYS, 0)
        self._gauges: dict[str, dict[str, int]] = {
            "by_stage_count": dict.fromkeys(ALL_STAGES, 0),
        }
        self._histograms: dict[str, deque[float]] = {
            k: deque(maxlen=HISTOGRAM_MAX_SAMPLES) for k in HISTOGRAM_KEYS
        }

    # ── Counters ──────────────────────────────────────────────────

    def inc(self, name: str, n: int = 1) -> None:
        """Increment a counter by ``n``. No-op for unknown names."""
        with self._lock:
            if name in self._counters:
                self._counters[name] += n

    def counter_value(self, name: str) -> int:
        with self._lock:
            return self._counters.get(name, 0)

    def reset_counters(self) -> None:
        with self._lock:
            for k in self._counters:
                self._counters[k] = 0

    def reset_histograms(self) -> None:
        """Clear all histogram ring buffers. Useful for test isolation."""
        with self._lock:
            for k in self._histograms:
                self._histograms[k].clear()

    # ── Gauges ────────────────────────────────────────────────────

    def set_stage_counts(self, counts: dict[str, int]) -> None:
        """Replace ``by_stage_count`` with ``counts`` (missing keys → 0)."""
        with self._lock:
            stage_map = self._gauges["by_stage_count"]
            stage_map.clear()
            for s in ALL_STAGES:
                stage_map[s] = int(counts.get(s, 0))

    def stage_count(self, stage: str) -> int:
        with self._lock:
            return int(self._gauges["by_stage_count"].get(stage, 0))

    # ── Histograms ────────────────────────────────────────────────

    def observe(self, name: str, value: float) -> None:
        """Record one sample. No-op for unknown names."""
        with self._lock:
            buf = self._histograms.get(name)
            if buf is not None:
                buf.append(float(value))

    def histogram_summary(self, name: str) -> dict[str, float]:
        with self._lock:
            buf = self._histograms.get(name)
            if not buf:
                return {"count": 0, "avg": 0.0, "p50": 0.0, "p99": 0.0}
            samples = sorted(buf)
            count = len(samples)
            avg = sum(samples) / count
            p50 = samples[count // 2]
            # Nearest-rank percentile: p99 of n samples is samples[int(0.99 * n)]
            # (clamped to the last index). For n=3 this gives the 3rd sample.
            p99_idx = max(0, min(count - 1, int(count * 0.99)))
            p99 = samples[p99_idx]
            return {"count": count, "avg": avg, "p50": p50, "p99": p99}

    # ── Snapshot ──────────────────────────────────────────────────

    def snapshot(self) -> dict[str, object]:
        """Return a JSON-serialisable snapshot of all metrics."""
        with self._lock:
            counters = dict(self._counters)
            gauges = {k: dict(v) for k, v in self._gauges.items()}
            histograms = {k: self.histogram_summary(k) for k in self._histograms}
        return {
            "counters": counters,
            "gauges": gauges,
            "histograms": histograms,
        }

    # ── Optional manual override (for tests) ─────────────────────

    def _set_counter(self, name: str, value: int) -> None:
        """Test helper: set a counter to an explicit value."""
        with self._lock:
            if name in self._counters:
                self._counters[name] = value


# Module-level singleton (shared between trigger code, scheduler jobs,
# and the API endpoint).
kl_metrics = KLMetrics()


__all__ = [
    "ALL_STAGES",
    "COUNTER_KEYS",
    "HISTOGRAM_KEYS",
    "HISTOGRAM_MAX_SAMPLES",
    "KLMetrics",
    "kl_metrics",
]

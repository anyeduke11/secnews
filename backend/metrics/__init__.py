"""KL trigger metrics package (Phase 10).

Provides a minimal in-process metrics collector for the T1/T2 (and
later T3–T5) lifecycle triggers. We deliberately do not depend on the
``prometheus_client`` package — the dashboard reads
``/api/kl/metrics`` and renders JSON directly, and the trigger code only
needs monotonic counters + a small ring-buffered latency histogram.
"""
from .kl_metrics import KLMetrics, kl_metrics

__all__ = ["KLMetrics", "kl_metrics"]

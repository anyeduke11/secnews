"""KL (Knowledge Lifecycle) trigger package.

Phase 10 — T1 and T2 triggers drive the knowledge_items.lifecycle column
from ``kl:raw`` → ``kl:refine`` → ``kl:link``.  T3–T5 will land in Phase 12.

Public surface
--------------
- :class:`T1Trigger` — raw → refine (simhash dedup + score + tag)
- :class:`T2Trigger` — refine → link (concept matching + knowledge_links)

Both classes expose a single :meth:`run_once` entry point.  They are
state-free apart from constructor-injected collaborators (metrics, retry
policy, dedup helpers), so the scheduler can instantiate them per-tick.
"""
from __future__ import annotations

from backend.services.triggers.t1_raw_to_refine import T1Trigger
from backend.services.triggers.t2_refine_to_link import T2Trigger

__all__ = ["T1Trigger", "T2Trigger"]

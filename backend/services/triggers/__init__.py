"""KL (Knowledge Lifecycle) trigger package.

Phase 12 — T1–T5 triggers drive the knowledge_items.lifecycle column
from ``kl:raw`` → ``kl:refine`` → ``kl:link`` → ``kl:structure``
→ ``kl:publish``.

Public surface
--------------
- :class:`T1Trigger` — raw → refine (simhash dedup + score + tag)
- :class:`T2Trigger` — refine → link (concept matching + knowledge_links)
- :class:`T3Trigger` — link → structure (link-count check + summary)
- :class:`T4Trigger` — structure → publish (score gate + stability window + .md write)
- :class:`T5Trigger` — publish → refine (rollback for failed items)

All classes expose a single :meth:`run_once` entry point.  They are
state-free apart from constructor-injected collaborators (metrics, retry
policy, dedup helpers), so the scheduler can instantiate them per-tick.
"""
from __future__ import annotations

from backend.services.triggers.t1_raw_to_refine import T1Trigger
from backend.services.triggers.t2_refine_to_link import T2Trigger
from backend.services.triggers.t3_link_to_structure import T3Trigger
from backend.services.triggers.t4_structure_to_publish import T4Trigger
from backend.services.triggers.t5_publish_to_refine import T5Trigger

__all__ = ["T1Trigger", "T2Trigger", "T3Trigger", "T4Trigger", "T5Trigger"]

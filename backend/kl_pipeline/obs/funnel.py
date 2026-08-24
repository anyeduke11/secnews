"""Funnel statistics — count items per KL stage.

Reads the knowledge/ directory to count how many items are in each
stage of the pipeline lifecycle.
"""
from __future__ import annotations

from typing import Any

from backend.kl_pipeline.queue import STAGES


def funnel_stats(wiki_fs: Any) -> list[dict]:
    """Return per-stage item counts from the wiki filesystem.

    Returns:
        [{"stage": "kl:raw", "count": 4149}, ...]
    """
    counts: dict[str, int] = {s: 0 for s in STAGES}

    if wiki_fs is None:
        return [{"stage": s, "count": c} for s, c in counts.items()]

    try:
        for item_id in wiki_fs.list_ids():
            doc = wiki_fs.read_item(item_id)
            if doc is None:
                counts["kl:raw"] += 1
                continue
            stage = doc["fm"].get("kl_stage", "kl:raw")
            if stage in counts:
                counts[stage] += 1
            else:
                counts["kl:raw"] += 1
    except Exception:
        pass

    return [{"stage": s, "count": c} for s, c in counts.items()]

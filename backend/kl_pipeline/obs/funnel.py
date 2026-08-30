"""Funnel statistics — count items per KL stage.

Reads the wiki archive root (llm-wiki-2.0) to count how many items are
in each stage of the pipeline lifecycle.
"""
from __future__ import annotations

from typing import Any

from backend.kl_pipeline.queue import STAGES
from backend.wiki_fs.contract import get_lifecycle

# 迁移 046 只在 DB 侧归一 lifecycle, wiki md frontmatter 从未被改写 ——
# 实测仍有 175 个 pre-v1.7 值 (generate 124 / signal 48 / amplify:tagged 3)。
# 旧实现把所有"不认识的值"计入 kl:raw, 心跳条因此把 175 报成待判读积压,
# 而 DB 里真正的 kl:raw 只有 2 条: 数据漂移被藏成了一个假数字。
_LEGACY_TO_STAGE = {
    "signal": "kl:raw",
    "amplify:tagged": "kl:refine",
    "generate": "kl:structure",
}

# 值域外 / 读不出的项归到这里, 让漂移在 UI 上可见而不是污染 kl:raw。
UNKNOWN_STAGE = "unknown"


def funnel_stats(wiki_fs: Any) -> list[dict]:
    """Return per-stage item counts from the wiki filesystem.

    Returns:
        ``[{"stage": "kl:raw", "count": 2}, ..., {"stage": "unknown", "count": n}]``
    """
    counts: dict[str, int] = dict.fromkeys(STAGES, 0)
    counts[UNKNOWN_STAGE] = 0

    if wiki_fs is None:
        return [{"stage": s, "count": c} for s, c in counts.items()]

    try:
        for item_id in wiki_fs.list_ids():
            doc = wiki_fs.read_item(item_id)
            if doc is None:
                counts[UNKNOWN_STAGE] += 1
                continue
            stage = get_lifecycle(doc["fm"])
            stage = _LEGACY_TO_STAGE.get(stage, stage)
            counts[stage if stage in counts else UNKNOWN_STAGE] += 1
    except Exception:
        pass

    return [{"stage": s, "count": c} for s, c in counts.items()]

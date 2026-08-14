"""KL (Knowledge Lifecycle) 5-stage state machine.

Phase 10 — T1/T2 triggers depend on this module for safe lifecycle transitions.

The 5 stages form a single forward DAG plus a T5 rollback edge:
    kl:raw → kl:refine → kl:link → kl:structure → kl:publish
                                                  ↑     ↓
                                                  └── T5 rollback to kl:refine

This module is **pure-Python** with no I/O. The actual database update is
performed by callers (triggers / MCP tools) after they verify a transition is
legal via :func:`can_transition`.

Conventions
-----------
- Stage values are lowercase strings prefixed with ``kl:`` to distinguish
  them from the legacy 3-stage values (``signal`` / ``amplify:tagged`` /
  ``generate``) defined in ``backend.domain.knowledge_models``.
- :data:`TRANSITIONS` is the source of truth for legal edges.
- :func:`transition` raises :class:`ValueError` on illegal moves; callers
  should let the exception bubble up to the retry policy / dead-letter
  queue, not silently swallow it.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Stage constants
# ---------------------------------------------------------------------------

# v1.7 5 阶段 lifecycle 值
LIFECYCLE_RAW = "kl:raw"            # 原始入库（从 hotspots / 收藏导入）
LIFECYCLE_REFINE = "kl:refine"      # 评分 + tag 完成
LIFECYCLE_LINK = "kl:link"          # 实体关联完成
LIFECYCLE_STRUCTURE = "kl:structure"  # 摘要 + 结构化完成
LIFECYCLE_PUBLISH = "kl:publish"    # 已发布到 knowledge/{item_id}.md


# All known 5-stage values (used for validation, e.g. when migrating from
# the legacy 3-stage model in 046_lifecycle_v2.sql).
ALL_STAGES: frozenset[str] = frozenset({
    LIFECYCLE_RAW,
    LIFECYCLE_REFINE,
    LIFECYCLE_LINK,
    LIFECYCLE_STRUCTURE,
    LIFECYCLE_PUBLISH,
})


# Legacy 3-stage values (kept for compatibility with existing rows before
# the 046 migration runs). T1/T2 treat these as "raw-like" so unfinished
# 046 migration does not block the triggers.
LEGACY_RAW_LIKE = "signal"
LEGACY_REFINE_LIKE = "amplify:tagged"
LEGACY_STRUCTURE_LIKE = "generate"

# ---------------------------------------------------------------------------
# Transition graph
# ---------------------------------------------------------------------------

# Forward DAG: T1 raw→refine, T2 refine→link, T3 link→structure (Phase 12),
# T4 structure→publish (Phase 12). T5 publish→refine is the user rollback
# edge (Phase 12).
TRANSITIONS: dict[str, frozenset[str]] = {
    LIFECYCLE_RAW:       frozenset({LIFECYCLE_REFINE}),
    LIFECYCLE_REFINE:    frozenset({LIFECYCLE_LINK}),
    LIFECYCLE_LINK:      frozenset({LIFECYCLE_STRUCTURE}),
    LIFECYCLE_STRUCTURE: frozenset({LIFECYCLE_PUBLISH}),
    LIFECYCLE_PUBLISH:   frozenset({LIFECYCLE_REFINE}),  # T5 rollback
}

# Build reverse map: for each (dst) → set of (src) that can move into it.
_REVERSE_BUILD: dict[str, set] = {}
for _src, _dsts in TRANSITIONS.items():
    for _dst in _dsts:
        _REVERSE_BUILD.setdefault(_dst, set()).add(_src)
REVERSE_TRANSITIONS: dict[str, frozenset[str]] = {
    k: frozenset(v) for k, v in _REVERSE_BUILD.items()
}


# Trigger name → expected (from, to) edge. Used by triggers for
# self-validation and by the dead-letter policy to know which stage to
# mark on a failed attempt.
TRIGGER_EDGES: dict[str, tuple] = {
    "t1": (LIFECYCLE_RAW, LIFECYCLE_REFINE),
    "t2": (LIFECYCLE_REFINE, LIFECYCLE_LINK),
    # Phase 12:
    "t3": (LIFECYCLE_LINK, LIFECYCLE_STRUCTURE),
    "t4": (LIFECYCLE_STRUCTURE, LIFECYCLE_PUBLISH),
    "t5": (LIFECYCLE_PUBLISH, LIFECYCLE_REFINE),  # rollback
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def can_transition(from_stage: str, to_stage: str) -> bool:
    """Return True iff ``from_stage → to_stage`` is a legal edge.

    Treats unknown stages as non-transitionable (returns False instead of
    raising) so callers can safely pass legacy values like ``signal`` and
    get a deterministic no-op.
    """
    return to_stage in TRANSITIONS.get(from_stage, frozenset())


def transition(
    item_lifecycle: str,
    to_stage: str,
    actor: str = "trigger",
) -> str:
    """Validate a transition and return ``to_stage`` if legal.

    The function does NOT modify the database — it is a pure validator
    that callers (triggers) use to assert legality before issuing an
    ``UPDATE knowledge_items SET lifecycle = ?`` SQL.

    Parameters
    ----------
    item_lifecycle : str
        The current lifecycle value of the item (e.g. ``kl:raw``).
    to_stage : str
        The proposed next stage (e.g. ``kl:refine``).
    actor : str
        Free-form identifier for the caller (logged in the error).

    Returns
    -------
    str
        The validated ``to_stage`` value (caller can use it directly in SQL).

    Raises
    ------
    ValueError
        If the transition is illegal. The error message includes both
        stages and the actor, which makes it easy to grep dead-letter
        entries.
    """
    if not can_transition(item_lifecycle, to_stage):
        raise ValueError(
            f"illegal KL transition: {item_lifecycle!r} -> {to_stage!r} "
            f"(by {actor})"
        )
    return to_stage


def is_terminal(stage: str) -> bool:
    """Return True for stages that should not be auto-advanced further.

    Currently only ``kl:publish`` is "terminal" in the forward direction;
    it can still be moved back to ``kl:refine`` via the T5 rollback
    trigger (Phase 12).
    """
    return stage == LIFECYCLE_PUBLISH


def predecessors(stage: str) -> frozenset[str]:
    """Return the set of stages that can transition INTO ``stage``."""
    return REVERSE_TRANSITIONS.get(stage, frozenset())


def successors(stage: str) -> frozenset[str]:
    """Return the set of stages reachable in one step from ``stage``."""
    return TRANSITIONS.get(stage, frozenset())


def is_valid_stage(stage: str | None) -> bool:
    """Return True if ``stage`` is one of the 5 known v1.7 values.

    Legacy 3-stage values (``signal`` / ``amplify:tagged`` / ``generate``)
    return False — they must be migrated by ``046_lifecycle_v2.sql`` first.
    """
    return stage in ALL_STAGES


# ---------------------------------------------------------------------------
# Display labels
# ---------------------------------------------------------------------------

STAGE_LABELS: dict[str, str] = {
    LIFECYCLE_RAW:       "原始",
    LIFECYCLE_REFINE:    "精炼",
    LIFECYCLE_LINK:      "关联",
    LIFECYCLE_STRUCTURE: "结构化",
    LIFECYCLE_PUBLISH:   "已发布",
}

STAGE_LABELS_EN: dict[str, str] = {
    LIFECYCLE_RAW:       "raw",
    LIFECYCLE_REFINE:    "refine",
    LIFECYCLE_LINK:      "link",
    LIFECYCLE_STRUCTURE: "structure",
    LIFECYCLE_PUBLISH:   "publish",
}


def label(stage: str, lang: str = "zh") -> str:
    """Return the human label for ``stage`` (defaults to Chinese)."""
    table = STAGE_LABELS if lang == "zh" else STAGE_LABELS_EN
    return table.get(stage, stage)


__all__ = [
    "ALL_STAGES",
    "LEGACY_RAW_LIKE",
    "LEGACY_REFINE_LIKE",
    "LEGACY_STRUCTURE_LIKE",
    "LIFECYCLE_LINK",
    "LIFECYCLE_PUBLISH",
    # Constants
    "LIFECYCLE_RAW",
    "LIFECYCLE_REFINE",
    "LIFECYCLE_STRUCTURE",
    "REVERSE_TRANSITIONS",
    # Display
    "STAGE_LABELS",
    "STAGE_LABELS_EN",
    # Graph
    "TRANSITIONS",
    "TRIGGER_EDGES",
    # API
    "can_transition",
    "is_terminal",
    "is_valid_stage",
    "label",
    "predecessors",
    "successors",
    "transition",
]

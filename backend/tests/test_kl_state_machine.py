"""Unit tests for the KL 5-stage state machine.

Covers
------
- All 5 legal forward transitions (T1–T4) + the T5 rollback edge
- 5 illegal transitions (e.g. raw → publish, publish → raw)
- is_terminal: only kl:publish
- is_valid_stage: accepts the 5 v1.7 values, rejects legacy values
- transition() returns the new stage on success
- transition() raises ValueError on illegal moves (with actor in message)
- predecessors / successors (graph reachability)
- label() returns Chinese (default) and English labels
- Edge: unknown stage → can_transition returns False; transition raises

Markers
-------
- ``pytest.mark.unit`` (set in pytest.ini or via pyproject)
"""
from __future__ import annotations

import pytest

from backend.services.kl_state_machine import (
    ALL_STAGES,
    LIFECYCLE_DEDUPED,
    LIFECYCLE_LINK,
    LIFECYCLE_PUBLISH,
    LIFECYCLE_RAW,
    LIFECYCLE_REFINE,
    LIFECYCLE_STRUCTURE,
    REVERSE_TRANSITIONS,
    STAGE_LABELS,
    STAGE_LABELS_EN,
    TRANSITIONS,
    TRIGGER_EDGES,
    can_transition,
    is_terminal,
    is_valid_stage,
    label,
    predecessors,
    successors,
    transition,
)

# ===========================================================================
# Constants sanity
# ===========================================================================

class TestConstants:
    def test_all_stages_has_5_entries(self):
        assert len(ALL_STAGES) == 5

    def test_all_stages_contains_known_values(self):
        assert frozenset({
            LIFECYCLE_RAW, LIFECYCLE_REFINE, LIFECYCLE_LINK,
            LIFECYCLE_STRUCTURE, LIFECYCLE_PUBLISH,
        }) == ALL_STAGES

    def test_all_stages_have_kl_prefix(self):
        for s in ALL_STAGES:
            assert s.startswith("kl:"), f"stage {s!r} missing kl: prefix"

    def test_transitions_has_5_keys(self):
        assert len(TRANSITIONS) == 5

    def test_trigger_edges_has_5_entries(self):
        # t1, t2 (Phase 10) + t3, t4, t5 (Phase 12)
        assert set(TRIGGER_EDGES.keys()) == {"t1", "t2", "t3", "t4", "t5"}


# ===========================================================================
# Legal forward transitions (T1-T4)
# ===========================================================================

class TestLegalTransitions:
    @pytest.mark.parametrize("from_stage,to_stage", [
        (LIFECYCLE_RAW, LIFECYCLE_REFINE),         # T1
        (LIFECYCLE_REFINE, LIFECYCLE_LINK),         # T2
        (LIFECYCLE_LINK, LIFECYCLE_STRUCTURE),      # T3 (Phase 12)
        (LIFECYCLE_STRUCTURE, LIFECYCLE_PUBLISH),   # T4 (Phase 12)
    ])
    def test_forward_legal(self, from_stage, to_stage):
        assert can_transition(from_stage, to_stage) is True

    def test_t5_rollback_legal(self):
        # kl:publish -> kl:refine is the T5 user-rollback edge
        assert can_transition(LIFECYCLE_PUBLISH, LIFECYCLE_REFINE) is True

    def test_t1_specifically(self):
        assert TRIGGER_EDGES["t1"] == (LIFECYCLE_RAW, LIFECYCLE_REFINE)

    def test_t2_specifically(self):
        assert TRIGGER_EDGES["t2"] == (LIFECYCLE_REFINE, LIFECYCLE_LINK)


# ===========================================================================
# Illegal transitions
# ===========================================================================

class TestIllegalTransitions:
    def test_raw_to_publish(self):
        assert can_transition(LIFECYCLE_RAW, LIFECYCLE_PUBLISH) is False

    def test_raw_to_link(self):
        assert can_transition(LIFECYCLE_RAW, LIFECYCLE_LINK) is False

    def test_publish_to_raw(self):
        # Backward by more than one stage is illegal
        assert can_transition(LIFECYCLE_PUBLISH, LIFECYCLE_RAW) is False

    def test_self_loop(self):
        # raw -> raw is not in TRANSITIONS
        assert can_transition(LIFECYCLE_RAW, LIFECYCLE_RAW) is False

    def test_publish_to_structure(self):
        # publish -> structure is illegal; only publish -> refine is allowed
        assert can_transition(LIFECYCLE_PUBLISH, LIFECYCLE_STRUCTURE) is False

    def test_transition_raises_value_error(self):
        with pytest.raises(ValueError) as exc_info:
            transition(LIFECYCLE_RAW, LIFECYCLE_PUBLISH, actor="t1")
        assert "kl:raw" in str(exc_info.value)
        assert "kl:publish" in str(exc_info.value)
        assert "t1" in str(exc_info.value)

    def test_transition_returns_to_stage_on_success(self):
        result = transition(LIFECYCLE_RAW, LIFECYCLE_REFINE, actor="t1")
        assert result == LIFECYCLE_REFINE

    def test_unknown_from_stage_cannot_transition(self):
        # Legacy value 'signal' is not in TRANSITIONS keys → safe no-op
        assert can_transition("signal", LIFECYCLE_REFINE) is False

    def test_unknown_to_stage_cannot_transition(self):
        with pytest.raises(ValueError):
            transition(LIFECYCLE_RAW, "kl:unknown")


# ===========================================================================
# is_terminal
# ===========================================================================

class TestIsTerminal:
    def test_publish_is_terminal(self):
        assert is_terminal(LIFECYCLE_PUBLISH) is True

    def test_deduped_is_terminal(self):
        """判重出口终态: 不该被任何 trigger / sweep 再推进。"""
        assert is_terminal(LIFECYCLE_DEDUPED) is True

    @pytest.mark.parametrize("stage", [
        LIFECYCLE_RAW, LIFECYCLE_REFINE, LIFECYCLE_LINK, LIFECYCLE_STRUCTURE,
    ])
    def test_other_stages_not_terminal(self, stage):
        assert is_terminal(stage) is False

    def test_unknown_stage_not_terminal(self):
        assert is_terminal("kl:unknown") is False


# ===========================================================================
# is_valid_stage
# ===========================================================================

class TestIsValidStage:
    @pytest.mark.parametrize("stage", [
        LIFECYCLE_RAW, LIFECYCLE_REFINE, LIFECYCLE_LINK,
        LIFECYCLE_STRUCTURE, LIFECYCLE_PUBLISH,
    ])
    def test_valid_stages(self, stage):
        assert is_valid_stage(stage) is True

    @pytest.mark.parametrize("stage", [
        "signal", "amplify:tagged", "generate", "kl:unknown", "", None,
    ])
    def test_invalid_stages(self, stage):
        assert is_valid_stage(stage) is False


# ===========================================================================
# Graph helpers
# ===========================================================================

class TestGraphHelpers:
    def test_successors_of_raw(self):
        # refine 是正常推进; deduped 是 T1 判重出口的副作用终态 (v0.6.3 kl:deduped)
        assert successors(LIFECYCLE_RAW) == frozenset({
            LIFECYCLE_REFINE, LIFECYCLE_DEDUPED,
        })

    def test_successors_of_publish(self):
        # publish can only go to refine (T5 rollback)
        assert successors(LIFECYCLE_PUBLISH) == frozenset({LIFECYCLE_REFINE})

    def test_successors_of_unknown(self):
        assert successors("kl:unknown") == frozenset()

    def test_predecessors_of_refine(self):
        # refine is reachable from raw (T1) and publish (T5)
        assert predecessors(LIFECYCLE_REFINE) == frozenset({
            LIFECYCLE_RAW, LIFECYCLE_PUBLISH,
        })

    def test_predecessors_of_raw(self):
        # raw has no predecessor (entry point)
        assert predecessors(LIFECYCLE_RAW) == frozenset()

    def test_predecessors_of_structure(self):
        assert predecessors(LIFECYCLE_STRUCTURE) == frozenset({LIFECYCLE_LINK})

    def test_reverse_transitions_consistent(self):
        # Reverse map should be the inverse of forward
        for src, dsts in TRANSITIONS.items():
            for dst in dsts:
                assert src in REVERSE_TRANSITIONS[dst]


# ===========================================================================
# Labels
# ===========================================================================

class TestLabels:
    def test_chinese_labels_have_5_entries(self):
        assert len(STAGE_LABELS) == 5
        for s in ALL_STAGES:
            assert s in STAGE_LABELS

    def test_english_labels_have_5_entries(self):
        assert len(STAGE_LABELS_EN) == 5

    def test_label_zh_default(self):
        assert label(LIFECYCLE_RAW) == "原始"
        assert label(LIFECYCLE_REFINE) == "精炼"
        assert label(LIFECYCLE_LINK) == "关联"
        assert label(LIFECYCLE_STRUCTURE) == "结构化"
        assert label(LIFECYCLE_PUBLISH) == "已发布"

    def test_label_en(self):
        assert label(LIFECYCLE_RAW, lang="en") == "raw"
        assert label(LIFECYCLE_REFINE, lang="en") == "refine"

    def test_label_unknown_falls_back_to_input(self):
        assert label("kl:unknown") == "kl:unknown"

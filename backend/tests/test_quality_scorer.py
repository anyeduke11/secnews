"""Quality scorer 单元测试。"""
from __future__ import annotations

from backend.quality.scorer import (
    compute_final_score,
    is_acceptable,
    merge_flags,
)


# ---------------------------------------------------------------------------
# compute_final_score
# ---------------------------------------------------------------------------
def test_compute_final_score_zero_deduction():
    assert compute_final_score(100, []) == 100


def test_compute_final_score_basic():
    assert compute_final_score(100, [10, 20, 30]) == 40


def test_compute_final_score_clamps_to_zero():
    assert compute_final_score(100, [200]) == 0


def test_compute_final_score_skips_none():
    assert compute_final_score(100, [None, 50, None]) == 50


def test_compute_final_score_custom_base():
    assert compute_final_score(80, [20, 10]) == 50


# ---------------------------------------------------------------------------
# merge_flags
# ---------------------------------------------------------------------------
def test_merge_flags_empty():
    assert merge_flags() == []


def test_merge_flags_single_list():
    assert merge_flags(["a", "b"]) == ["a", "b"]


def test_merge_flags_dedup_preserves_order():
    assert merge_flags(["a", "b"], ["b", "c"]) == ["a", "b", "c"]


def test_merge_flags_three_lists():
    assert merge_flags(["x"], ["y", "x"], ["z"]) == ["x", "y", "z"]


def test_merge_flags_skips_empty_strings():
    assert merge_flags(["a", ""], ["", "b"]) == ["a", "b"]


def test_merge_flags_skips_none_entries():
    assert merge_flags(["a", None], [None, "b"]) == ["a", "b"]


# ---------------------------------------------------------------------------
# is_acceptable
# ---------------------------------------------------------------------------
def test_is_acceptable_default_threshold():
    assert is_acceptable(30) is True
    assert is_acceptable(29) is False
    assert is_acceptable(100) is True
    assert is_acceptable(0) is False


def test_is_acceptable_custom_threshold():
    assert is_acceptable(50, threshold=50) is True
    assert is_acceptable(49, threshold=50) is False
    assert is_acceptable(80, threshold=70) is True

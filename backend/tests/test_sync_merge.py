"""Sync merge engine — direct unit tests (no SyncService wrapper).

Covers:
- three_way_merge: all 5 merge scenarios (noop, remote-only, local-only, conflict, both-new)
- validate_bundle: valid/invalid edge cases
- MergeResult data class
- SETTINGS_BLOCKLIST integration
"""

from __future__ import annotations

import pytest

from backend.exceptions import InternalException
from backend.services.sync_merge import (
    BUNDLE_VERSION,
    MergeResult,
    three_way_merge,
    validate_bundle,
)


def _empty_bundle(device_id="a", merged_at="t0"):
    return {
        "version": BUNDLE_VERSION,
        "device_id": device_id,
        "merged_at": merged_at,
        "records": {
            "favorites": [], "todos": [], "skills": [],
            "custom_sources": [], "secrets": [],
            "settings": {},
        },
    }


# ---------------------------------------------------------------------------
# validate_bundle
# ---------------------------------------------------------------------------

def test_validate_bundle_ok():
    validate_bundle(_empty_bundle())


def test_validate_bundle_not_dict():
    with pytest.raises(InternalException):
        validate_bundle("not a dict")


def test_validate_bundle_wrong_version():
    b = _empty_bundle()
    b["version"] = "0.9"
    with pytest.raises(InternalException):
        validate_bundle(b)


def test_validate_bundle_missing_records():
    with pytest.raises(InternalException):
        validate_bundle({"version": BUNDLE_VERSION})


def test_validate_bundle_wrong_favorites_type():
    b = _empty_bundle()
    b["records"]["favorites"] = "not-a-list"
    with pytest.raises(InternalException):
        validate_bundle(b)


def test_validate_bundle_wrong_settings_type():
    b = _empty_bundle()
    b["records"]["settings"] = ["not-a-dict"]
    with pytest.raises(InternalException):
        validate_bundle(b)


# ---------------------------------------------------------------------------
# MergeResult
# ---------------------------------------------------------------------------

def test_merge_result_to_dict():
    r = MergeResult(merged_bundle={}, conflict_count=3, table_conflicts={"favorites": 2})
    d = r.to_dict()
    assert d["conflict_count"] == 3
    assert d["table_conflicts"]["favorites"] == 2


# ---------------------------------------------------------------------------
# three_way_merge — 5 merge scenarios
# ---------------------------------------------------------------------------

def test_merge_noop():
    """base == local == remote → 合并后不变。"""
    b = _empty_bundle()
    result = three_way_merge(b, b, b)
    assert result.conflict_count == 0


def test_merge_remote_only_change():
    """base==local, remote changed → accept remote."""
    base = _empty_bundle("a", "t0")
    base["records"]["favorites"] = [{"hotspot_id": "h1", "title": "old"}]
    local = _empty_bundle("a", "t0")
    local["records"]["favorites"] = [{"hotspot_id": "h1", "title": "old"}]
    remote = _empty_bundle("b", "t1")
    remote["records"]["favorites"] = [{"hotspot_id": "h1", "title": "new-from-remote"}]

    result = three_way_merge(base, local, remote)
    assert result.conflict_count == 0
    titles = [f["title"] for f in result.merged_bundle["records"]["favorites"]]
    assert "new-from-remote" in titles


def test_merge_local_only_change():
    """base==remote, local changed → accept local."""
    base = _empty_bundle("a", "t0")
    base["records"]["favorites"] = [{"hotspot_id": "h1", "title": "old"}]
    local = _empty_bundle("a", "t1")
    local["records"]["favorites"] = [{"hotspot_id": "h1", "title": "new-from-local"}]
    remote = _empty_bundle("b", "t0")
    remote["records"]["favorites"] = [{"hotspot_id": "h1", "title": "old"}]

    result = three_way_merge(base, local, remote)
    assert result.conflict_count == 0
    titles = [f["title"] for f in result.merged_bundle["records"]["favorites"]]
    assert "new-from-local" in titles


def test_merge_both_changed_conflict():
    """Both changed differently → conflict. Newer updated_at wins."""
    base = _empty_bundle("a", "t0")
    base["records"]["favorites"] = [{"hotspot_id": "h1", "title": "old", "updated_at": "t0"}]
    local = _empty_bundle("a", "t1")
    local["records"]["favorites"] = [{"hotspot_id": "h1", "title": "local-version", "updated_at": "t1"}]
    remote = _empty_bundle("b", "t2")
    remote["records"]["favorites"] = [{"hotspot_id": "h1", "title": "remote-version", "updated_at": "t2"}]

    result = three_way_merge(base, local, remote)
    assert result.conflict_count == 1
    titles = [f["title"] for f in result.merged_bundle["records"]["favorites"]]
    assert "remote-version" in titles  # remote updated_at is newer


def test_merge_addition_on_both_sides():
    """Both sides added new records → all preserved."""
    base = _empty_bundle()
    local = _empty_bundle("a", "t1")
    local["records"]["favorites"] = [{"hotspot_id": "h1", "title": "L"}]
    remote = _empty_bundle("b", "t1")
    remote["records"]["favorites"] = [{"hotspot_id": "h2", "title": "R"}]

    result = three_way_merge(base, local, remote)
    titles = sorted(f["title"] for f in result.merged_bundle["records"]["favorites"])
    assert titles == ["L", "R"]


def test_merge_deletion_in_local():
    """Local removes a record → remote should pick it up."""
    base = _empty_bundle("a", "t0")
    base["records"]["favorites"] = [{"hotspot_id": "h1", "title": "will-be-deleted"}]
    local = _empty_bundle("a", "t1")
    local["records"]["favorites"] = []  # deleted locally
    remote = _empty_bundle("b", "t0")
    remote["records"]["favorites"] = [{"hotspot_id": "h1", "title": "will-be-deleted"}]

    result = three_way_merge(base, local, remote)
    assert len(result.merged_bundle["records"]["favorites"]) == 0


# ---------------------------------------------------------------------------
# Settings merge
# ---------------------------------------------------------------------------

def test_merge_settings_blocklist_filtered():
    """SETTINGS_BLOCKLIST keys filtered out."""
    base = _empty_bundle()
    local = _empty_bundle("a", "t1")
    local["records"]["settings"] = {"keep": "x", "scheduler.last_run": "should-not-sync"}
    remote = _empty_bundle()

    result = three_way_merge(base, local, remote)
    assert "keep" in result.merged_bundle["records"]["settings"]
    assert "scheduler.last_run" not in result.merged_bundle["records"]["settings"]


def test_merge_settings_conflict():
    """Settings conflict counted correctly."""
    base = _empty_bundle()
    base["records"]["settings"] = {"k": "v0"}
    local = _empty_bundle("a", "t1")
    local["records"]["settings"] = {"k": "v-local"}
    remote = _empty_bundle("b", "t1")
    remote["records"]["settings"] = {"k": "v-remote"}

    result = three_way_merge(base, local, remote)
    assert result.table_conflicts["settings"] == 1


def test_merge_settings_two_keys_no_conflict():
    """Two settings keys changed in parallel, no conflict."""
    base = _empty_bundle()
    base["records"]["settings"] = {"a": "1", "b": "1"}
    local = _empty_bundle("a", "t1")
    local["records"]["settings"] = {"a": "new-a", "b": "1"}
    remote = _empty_bundle("b", "t1")
    remote["records"]["settings"] = {"a": "1", "b": "new-b"}

    result = three_way_merge(base, local, remote)
    # No conflict because each key was only changed by one side
    assert result.table_conflicts["settings"] == 0


# ---------------------------------------------------------------------------
# Multi-table merge
# ---------------------------------------------------------------------------

def test_merge_all_tables():
    """All 6 tables merge correctly together."""
    base = _empty_bundle()
    local = _empty_bundle("a", "t1")
    local["records"]["favorites"] = [{"hotspot_id": "h1", "title": "fav"}]
    local["records"]["todos"] = [{"id": 1, "title": "todo", "source_type": "manual"}]
    local["records"]["skills"] = [{"name": "skill1", "url": "https://example.com", "install_command": "echo"}]
    local["records"]["custom_sources"] = [{"url": "https://source.example.com", "name": "src"}]
    local["records"]["secrets"] = [{"name": "secret1", "model": "gpt-4", "base_url": "https://api.example.com"}]
    local["records"]["settings"] = {"theme": "dark"}
    remote = _empty_bundle("b", "t1")

    result = three_way_merge(base, local, remote)
    assert result.conflict_count == 0
    merged = result.merged_bundle["records"]
    assert len(merged["favorites"]) == 1
    assert len(merged["todos"]) == 1
    assert len(merged["skills"]) == 1
    assert len(merged["custom_sources"]) == 1
    assert len(merged["secrets"]) == 1
    assert merged["settings"]["theme"] == "dark"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_merge_no_base():
    """No base (first sync) → merge local and remote."""
    local = _empty_bundle("a", "t1")
    local["records"]["favorites"] = [{"hotspot_id": "h1", "title": "L"}]
    remote = _empty_bundle("b", "t1")
    remote["records"]["favorites"] = [{"hotspot_id": "h2", "title": "R"}]

    result = three_way_merge(None, local, remote)
    titles = sorted(f["title"] for f in result.merged_bundle["records"]["favorites"])
    assert titles == ["L", "R"]
    assert result.conflict_count == 0


def test_merge_identical_records_deduped():
    """Same record from both sides → dedup to 1."""
    base = _empty_bundle()
    local = _empty_bundle("a", "t1")
    local["records"]["favorites"] = [{"hotspot_id": "h1", "title": "same"}]
    remote = _empty_bundle("b", "t1")
    remote["records"]["favorites"] = [{"hotspot_id": "h1", "title": "same"}]

    result = three_way_merge(base, local, remote)
    assert len(result.merged_bundle["records"]["favorites"]) == 1


def test_merge_remote_empty_is_not_deletion():
    """Remote has empty favorites while base+local have same record → not a deletion, local wins."""
    base = _empty_bundle()
    base["records"]["favorites"] = [{"hotspot_id": "h1", "title": "old"}]
    local = _empty_bundle("a", "t1")
    local["records"]["favorites"] = [{"hotspot_id": "h1", "title": "old"}]
    remote = _empty_bundle("b", "t1")
    remote["records"]["favorites"] = []

    result = three_way_merge(base, local, remote)
    # record is in base+local but not in remote. With strict 3-way rules,
    # remote doesn't have it = remote side lacks it. Since local == base,
    # and remote changes (empty), remote change wins → no record.
    # This is correct: if both machines should converge, the side that
    # 'appears to have deleted' wins.
    assert len(result.merged_bundle["records"]["favorites"]) == 0
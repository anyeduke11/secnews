"""Sync merge engine — 3-way merge for bundle records.

Design
------
Implements the 3-way merge (base/local/remote) logic for all syncable tables.
Separated from SyncService so it can be tested independently.

Merge rules (Q3 decision):
- Record-level: aligned by primary key (hotspot_id / source_type+source_id / name / url)
- Field-level: base==local, remote changed → accept remote; base==remote, local changed → accept local
- Conflict: both changed differently → newer updated_at wins, conflict count +1
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from backend.exceptions import InternalException

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BUNDLE_VERSION = "1.0"

# settings 黑名单: 永不跨端同步的 key
SETTINGS_BLOCKLIST = {
    "scheduler.last_run",
    "collector.last_run",
    "trend.last_rebuild",
    "sync_runtime_lock",
}


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------
@dataclass
class MergeResult:
    merged_bundle: dict
    conflict_count: int
    table_conflicts: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "conflict_count": self.conflict_count,
            "table_conflicts": self.table_conflicts,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Bundle validation
# ---------------------------------------------------------------------------
def validate_bundle(bundle: dict) -> None:
    """Validate bundle schema. Raises InternalException on mismatch."""
    if not isinstance(bundle, dict):
        raise InternalException("bundle 必须为 dict")
    if bundle.get("version") != BUNDLE_VERSION:
        raise InternalException(
            f"bundle version 不支持: {bundle.get('version')} (期望 {BUNDLE_VERSION})"
        )
    if "records" not in bundle or not isinstance(bundle["records"], dict):
        raise InternalException("bundle.records 缺失或格式错")
    for key in (
        "favorites", "todos", "skills", "custom_sources", "secrets",
        "codegarden_projects", "codegarden_services",
        # v1.7 Phase 6 Task 6.1
        "tags", "hotspot_tags", "reading_states", "annotations", "sm2_reviews",
    ):
        if key in bundle["records"] and not isinstance(bundle["records"][key], list):
            raise InternalException(f"bundle.records.{key} 必须为 list")
    if "settings" in bundle["records"] and not isinstance(
        bundle["records"]["settings"], dict
    ):
        raise InternalException("bundle.records.settings 必须为 dict")


# ---------------------------------------------------------------------------
# 3-way merge
# ---------------------------------------------------------------------------
def three_way_merge(
    base: Optional[dict], local: dict, remote: dict,
) -> MergeResult:
    """Merge base/local/remote → merged result.

    See module docstring for merge rules.
    """
    validate_bundle(local)
    validate_bundle(remote)

    merged_records: dict[str, Any] = {}
    total_conflicts = 0
    table_conflicts: dict[str, int] = {}

    # --- list-typed tables (last_writer_wins) ---
    for table, key_fn in (
        ("favorites", lambda r: r.get("hotspot_id")),
        ("todos", lambda r: f"{r.get('source_type')}::{r.get('source_id') or r.get('id')}"),
        ("skills", lambda r: r.get("name")),
        ("custom_sources", lambda r: r.get("url")),
        ("secrets", lambda r: r.get("name")),
        # v1.7 Phase 6 Task 6.1: last_writer_wins
        ("reading_states", lambda r: f"{r.get('entity_type')}::{r.get('entity_id')}"),
        ("annotations", lambda r: r.get("id")),
    ):
        base_recs = (base or {}).get("records", {}).get(table, []) or []
        local_recs = local.get("records", {}).get(table, []) or []
        remote_recs = remote.get("records", {}).get(table, []) or []
        merged, conflicts = _merge_records(base_recs, local_recs, remote_recs, key_fn)
        merged_records[table] = merged
        table_conflicts[table] = conflicts
        total_conflicts += conflicts

    # --- v1.7 Phase 6 Task 6.1: cascade merge for tags (reference data) ---
    for table, key_fn in (
        ("tags", lambda r: r.get("id")),
        ("hotspot_tags", lambda r: f"{r.get('hotspot_id')}::{r.get('tag_id')}"),
    ):
        merged, conflicts = _merge_cascade(
            (base or {}).get("records", {}).get(table, []) or [],
            local.get("records", {}).get(table, []) or [],
            remote.get("records", {}).get(table, []) or [],
            key_fn,
        )
        merged_records[table] = merged
        table_conflicts[table] = conflicts
        total_conflicts += conflicts

    # --- v1.7 Phase 6 Task 6.1: sm2_reviews (special merge: due_at 早者胜) ---
    sm2_base = (base or {}).get("records", {}).get("sm2_reviews", []) or []
    sm2_local = local.get("records", {}).get("sm2_reviews", []) or []
    sm2_remote = remote.get("records", {}).get("sm2_reviews", []) or []
    sm2_merged, sm2_conflicts = _merge_sm2_reviews(sm2_base, sm2_local, sm2_remote)
    merged_records["sm2_reviews"] = sm2_merged
    table_conflicts["sm2_reviews"] = sm2_conflicts
    total_conflicts += sm2_conflicts

    # --- settings (dict-typed) ---
    base_settings = (base or {}).get("records", {}).get("settings", {}) or {}
    local_settings = local.get("records", {}).get("settings", {}) or {}
    remote_settings = remote.get("records", {}).get("settings", {}) or {}
    merged_settings, settings_conflicts = _merge_settings(base_settings, local_settings, remote_settings)
    merged_records["settings"] = merged_settings
    table_conflicts["settings"] = settings_conflicts
    total_conflicts += settings_conflicts

    merged_bundle = {
        "version": BUNDLE_VERSION,
        "device_id": local.get("device_id") or remote.get("device_id"),
        "merged_at": _now_iso(),
        "records": merged_records,
    }
    return MergeResult(merged_bundle, total_conflicts, table_conflicts)


def _merge_records(base: list, local: list, remote: list, key_fn) -> tuple[list, int]:
    """Single-table 3-way merge. Returns (merged_records, conflict_count)."""
    base_by_key = {key_fn(r): r for r in base}
    local_by_key = {key_fn(r): r for r in local}
    remote_by_key = {key_fn(r): r for r in remote}

    all_keys = set(base_by_key) | set(local_by_key) | set(remote_by_key)
    merged: list = []
    conflicts = 0

    for k in all_keys:
        if k is None or k == "manual::None" or k == "::":
            for src in (base, local, remote):
                for r in src:
                    if key_fn(r) in (None, "manual::None", "::"):
                        merged.append(r)
            continue

        b = base_by_key.get(k)
        l = local_by_key.get(k)
        r = remote_by_key.get(k)

        if b is None and l is None and r is None:
            continue
        if l is None and r is None:
            continue
        if l is None:
            # l is None: could be local deletion (base has it) or new remote record
            if b is not None:
                # Local deleted the record → honor deletion, don't re-add from remote
                continue
            # Remote added a new record
            merged.append(r)
            continue
        if r is None:
            # r is None: could be remote deletion
            if b is not None:
                # Remote deleted the record → honor deletion
                continue
            # Local added a new record
            merged.append(l)
            continue
        if l == r:
            merged.append(l)
            continue

        # Field-level merge
        fields = set(l.keys()) | set(r.keys())
        field_merged: dict = {}
        had_conflict = False
        for f in fields:
            if f == "updated_at":
                l_ts = l.get(f) or ""
                r_ts = r.get(f) or ""
                field_merged[f] = max(l_ts, r_ts)
                continue
            lv = l.get(f)
            rv = r.get(f)
            bv = b.get(f) if b else None
            if lv == rv:
                if lv is not None:
                    field_merged[f] = lv
            elif lv == bv:
                if rv is not None:
                    field_merged[f] = rv
            elif rv == bv:
                if lv is not None:
                    field_merged[f] = lv
            else:
                had_conflict = True
                l_ts = l.get("updated_at") or ""
                r_ts = r.get("updated_at") or ""
                winner = l if l_ts >= r_ts else r
                field_merged[f] = winner.get(f)
        if "id" in (l.keys() | r.keys()):
            field_merged["id"] = l.get("id") or r.get("id")
        merged.append(field_merged)
        if had_conflict:
            conflicts += 1

    # Dedup (keep first occurrence)
    seen = set()
    deduped: list = []
    for r in merged:
        k = key_fn(r)
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)
    return deduped, conflicts


def _merge_settings(base: dict, local: dict, remote: dict) -> tuple[dict, int]:
    """Settings dict 3-way merge."""
    all_keys = set(base) | set(local) | set(remote)
    merged: dict = {}
    conflicts = 0
    for k in all_keys:
        if k in SETTINGS_BLOCKLIST:
            continue
        lv = local.get(k)
        rv = remote.get(k)
        bv = base.get(k)
        if lv == rv:
            if lv is not None:
                merged[k] = lv
        elif lv == bv:
            if rv is not None:
                merged[k] = rv
        elif rv == bv:
            if lv is not None:
                merged[k] = lv
        else:
            merged[k] = lv if lv is not None else rv
            conflicts += 1
    return merged, conflicts


# ---------------------------------------------------------------------------
# v1.7 Phase 6 Task 6.1: cascade + sm2 merge helpers
# ---------------------------------------------------------------------------
def _merge_cascade(base: list, local: list, remote: list, key_fn) -> tuple[list, int]:
    """Cascade merge (tags / hotspot_tags): 整表 union, 后写入者覆盖字段。

    适用场景: 静态参考数据 (tags) 和强一致关系表 (hotspot_tags)。
    - 删除信号: base 中存在但 local+remote 都不存在 → 视作删除
    - 添加: local/remote 任一新增 → 保留
    - 冲突: local 与 remote 都改了, base 不同 → field-level last-write-wins
    """
    base_by_key = {key_fn(r): r for r in base}
    local_by_key = {key_fn(r): r for r in local}
    remote_by_key = {key_fn(r): r for r in remote}

    all_keys = set(local_by_key) | set(remote_by_key)
    merged: list = []
    conflicts = 0
    for k in all_keys:
        if k is None:
            continue
        b = base_by_key.get(k)
        l = local_by_key.get(k)
        r = remote_by_key.get(k)

        # 删除信号: local/remote 都没了, base 还在 → 视作删除
        if l is None and r is None and b is not None:
            continue
        if l is None and r is None:
            continue
        if l is None:
            merged.append(r)
            continue
        if r is None:
            merged.append(l)
            continue
        if l == r:
            merged.append(l)
            continue

        # field-level last-write-wins by updated_at
        fields = set(l.keys()) | set(r.keys())
        field_merged: dict = {}
        had_conflict = False
        for f in fields:
            if f == "updated_at":
                l_ts = l.get(f) or ""
                r_ts = r.get(f) or ""
                field_merged[f] = max(l_ts, r_ts)
                continue
            lv = l.get(f)
            rv = r.get(f)
            bv = b.get(f) if b else None
            if lv == rv:
                if lv is not None:
                    field_merged[f] = lv
            elif lv == bv:
                if rv is not None:
                    field_merged[f] = rv
            elif rv == bv:
                if lv is not None:
                    field_merged[f] = lv
            else:
                had_conflict = True
                l_ts = l.get("updated_at") or ""
                r_ts = r.get("updated_at") or ""
                winner = l if l_ts >= r_ts else r
                field_merged[f] = winner.get(f)
        if "id" in (l.keys() | r.keys()):
            field_merged["id"] = l.get("id") or r.get("id")
        merged.append(field_merged)
        if had_conflict:
            conflicts += 1

    # Dedup (keep first occurrence)
    seen = set()
    deduped: list = []
    for r in merged:
        k = key_fn(r)
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)
    return deduped, conflicts


def _merge_sm2_reviews(base: list, local: list, remote: list) -> tuple[list, int]:
    """SM-2 复习合并: ``due_at`` 较早的胜出 (防覆盖未到期复习)。

    业务规则: SM-2 间隔复习中, due_at 越早表示越急需复习; 如果用户在两台设备上
    都进行过复习, 较早的 due_at 反映更近的复习状态, 必须保留。

    同样支持删除信号: local+remote 都没了, base 还在 → 删除。
    """
    def _key(r: dict) -> str:
        return r.get("id") or f"{r.get('entity_type')}::{r.get('entity_id')}"

    base_by_key = {_key(r): r for r in base}
    local_by_key = {_key(r): r for r in local}
    remote_by_key = {_key(r): r for r in remote}

    all_keys = set(local_by_key) | set(remote_by_key)
    merged: list = []
    conflicts = 0
    for k in all_keys:
        b = base_by_key.get(k)
        l = local_by_key.get(k)
        r = remote_by_key.get(k)

        if l is None and r is None and b is not None:
            continue
        if l is None and r is None:
            continue
        if l is None:
            merged.append(r)
            continue
        if r is None:
            merged.append(l)
            continue
        if l == r:
            merged.append(l)
            continue

        # 核心规则: due_at 较早的胜出
        l_due = l.get("due_at") or ""
        r_due = r.get("due_at") or ""
        if l_due and r_due:
            winner = l if l_due <= r_due else r
        elif l_due:
            winner = l
        elif r_due:
            winner = r
        else:
            winner = l  # both empty: default to local
        merged.append(winner)
        conflicts += 1 if l_due != r_due else 0

    # Dedup
    seen = set()
    deduped: list = []
    for r in merged:
        k = _key(r)
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)
    return deduped, conflicts


__all__ = [
    "MergeResult",
    "BUNDLE_VERSION",
    "SETTINGS_BLOCKLIST",
    "validate_bundle",
    "three_way_merge",
    "_now_iso",
    "_merge_cascade",          # v1.7 Phase 6
    "_merge_sm2_reviews",      # v1.7 Phase 6
]
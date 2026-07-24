"""v1.7 Phase 6 Task 6.1 — Sync Bundle 扩展测试.

覆盖:
- ``validate_bundle`` 接受 v1.7 新表 (tags/hotspot_tags/reading_states/annotations/sm2_reviews)
- ``three_way_merge``:
  - reading_states / annotations last_writer_wins
  - tags / hotspot_tags cascade merge
  - sm2_reviews 特殊规则 (due_at 早者胜出)
- ``build_bundle`` 包含 v1.7 新表字段
- ``apply_bundle`` v1.7 表的 upsert 行为 (含 sm2 due_at 守卫)
"""

from __future__ import annotations

import sqlite3
from typing import Iterator

import pytest

from backend.repository import db as db_mod
from backend.services.sync_merge import (
    BUNDLE_VERSION,
    MergeResult,
    _merge_cascade,
    _merge_sm2_reviews,
    three_way_merge,
    validate_bundle,
)


def _conn():
    """通过 db_mod 调用 patched get_connection, 避免引用原始函数。"""
    return db_mod.get_connection()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def db(tmp_path, monkeypatch) -> Iterator[None]:
    """建临时 DB + 跑全部迁移; get_connection 替换为单例连接."""
    db_file = tmp_path / "test_sync_v17.db"
    setup_conn = sqlite3.connect(str(db_file))
    schema_dir = "backend/repository/migrations"
    # 跑所有 001-036 迁移, 缺哪个就跳 (向后兼容)
    import re
    if (schema_dir_p := __import__("pathlib").Path(schema_dir)).exists():
        for sql_file in sorted(schema_dir_p.glob("*.sql")):
            with open(sql_file, "r", encoding="utf-8") as f:
                setup_conn.executescript(f.read())
    setup_conn.commit()
    setup_conn.close()

    from backend import repository as repo_pkg
    from backend.repository import db as db_mod

    shared_conn = sqlite3.connect(str(db_file), check_same_thread=False, timeout=30.0)
    shared_conn.row_factory = sqlite3.Row
    shared_conn.execute("PRAGMA journal_mode=WAL")
    shared_conn.execute("PRAGMA foreign_keys=ON")
    shared_conn.execute("PRAGMA busy_timeout=30000")

    def _get_conn():
        return shared_conn

    monkeypatch.setattr(db_mod, "get_connection", _get_conn)
    for name in list(repo_pkg.__dict__.keys()):
        m = getattr(repo_pkg, name)
        if hasattr(m, "get_connection"):
            try:
                monkeypatch.setattr(m, "get_connection", _get_conn)
            except (AttributeError, TypeError):
                pass
    yield
    shared_conn.close()


def _empty_bundle(device_id="a", merged_at="t0"):
    return {
        "version": BUNDLE_VERSION,
        "device_id": device_id,
        "merged_at": merged_at,
        "records": {
            "favorites": [], "todos": [], "skills": [],
            "custom_sources": [], "secrets": [],
            "tags": [], "hotspot_tags": [],
            "reading_states": [], "annotations": [], "sm2_reviews": [],
            "settings": {},
        },
    }


# ---------------------------------------------------------------------------
# validate_bundle — v1.7 新表
# ---------------------------------------------------------------------------
def test_validate_bundle_accepts_v17_tables():
    """v1.7 新表 (tags/hotspot_tags/reading_states/annotations/sm2_reviews) 通过验证。"""
    validate_bundle(_empty_bundle())


def test_validate_bundle_rejects_wrong_sm2_type():
    """sm2_reviews 不是 list 时报错。"""
    b = _empty_bundle()
    b["records"]["sm2_reviews"] = {"not": "a list"}
    with pytest.raises(Exception):
        validate_bundle(b)


def test_validate_bundle_rejects_wrong_tags_type():
    b = _empty_bundle()
    b["records"]["tags"] = "string-not-list"
    with pytest.raises(Exception):
        validate_bundle(b)


# ---------------------------------------------------------------------------
# reading_states / annotations — last_writer_wins
# ---------------------------------------------------------------------------
def test_merge_reading_states_last_writer_wins():
    """reading_states: updated_at 较新者胜出。"""
    base = _empty_bundle()
    base["records"]["reading_states"] = [
        {"entity_type": "hotspot", "entity_id": "h1",
         "opened_count": 1, "dwell_ms": 100,
         "last_read_at": "t0", "created_at": "t0", "updated_at": "t0"}
    ]
    local = _empty_bundle("a", "t0")
    local["records"]["reading_states"] = [
        {"entity_type": "hotspot", "entity_id": "h1",
         "opened_count": 2, "dwell_ms": 200,
         "last_read_at": "t0", "created_at": "t0", "updated_at": "t0"}
    ]
    remote = _empty_bundle("b", "t2")
    remote["records"]["reading_states"] = [
        {"entity_type": "hotspot", "entity_id": "h1",
         "opened_count": 5, "dwell_ms": 500,
         "last_read_at": "t2", "created_at": "t0", "updated_at": "t2"}
    ]
    result = three_way_merge(base, local, remote)
    states = result.merged_bundle["records"]["reading_states"]
    assert len(states) == 1
    # remote updated_at 更新, 胜出
    assert states[0]["opened_count"] == 5
    assert states[0]["dwell_ms"] == 500


def test_merge_annotations_id_aligned():
    """annotations 按 id 对齐, last_writer_wins."""
    base = _empty_bundle()
    base["records"]["annotations"] = [
        {"id": "a1", "entity_type": "knowledge", "entity_id": "k1",
         "content": "old", "created_at": "t0", "updated_at": "t0"}
    ]
    local = _empty_bundle("a", "t1")
    local["records"]["annotations"] = [
        {"id": "a1", "entity_type": "knowledge", "entity_id": "k1",
         "content": "local-edit", "created_at": "t0", "updated_at": "t1"}
    ]
    remote = _empty_bundle("b", "t2")
    remote["records"]["annotations"] = [
        {"id": "a1", "entity_type": "knowledge", "entity_id": "k1",
         "content": "remote-edit", "created_at": "t0", "updated_at": "t2"}
    ]
    result = three_way_merge(base, local, remote)
    anns = result.merged_bundle["records"]["annotations"]
    assert len(anns) == 1
    assert anns[0]["content"] == "remote-edit"


def test_merge_reading_states_addition():
    """两端都新增 reading_states → 保留全部。"""
    base = _empty_bundle()
    local = _empty_bundle("a", "t1")
    local["records"]["reading_states"] = [
        {"entity_type": "hotspot", "entity_id": "h1",
         "opened_count": 1, "dwell_ms": 0, "last_read_at": "t1",
         "created_at": "t1", "updated_at": "t1"}
    ]
    remote = _empty_bundle("b", "t1")
    remote["records"]["reading_states"] = [
        {"entity_type": "hotspot", "entity_id": "h2",
         "opened_count": 1, "dwell_ms": 0, "last_read_at": "t1",
         "created_at": "t1", "updated_at": "t1"}
    ]
    result = three_way_merge(base, local, remote)
    keys = {(s["entity_type"], s["entity_id"]) for s in result.merged_bundle["records"]["reading_states"]}
    assert keys == {("hotspot", "h1"), ("hotspot", "h2")}


# ---------------------------------------------------------------------------
# tags / hotspot_tags — cascade merge
# ---------------------------------------------------------------------------
def test_merge_cascade_union_addition():
    """cascade: 两端各加一个 tag → 合并后两个都在。"""
    base = _empty_bundle()
    local = _empty_bundle("a", "t1")
    local["records"]["tags"] = [{"id": "t1", "label": "L-Tag", "type": "domain", "weight": 1.0}]
    remote = _empty_bundle("b", "t1")
    remote["records"]["tags"] = [{"id": "t2", "label": "R-Tag", "type": "domain", "weight": 1.0}]
    result = three_way_merge(base, local, remote)
    ids = {t["id"] for t in result.merged_bundle["records"]["tags"]}
    assert ids == {"t1", "t2"}


def test_merge_cascade_field_conflict():
    """cascade: 双方改同一字段 → field-level last-write-wins (updated_at)."""
    base = _empty_bundle()
    base["records"]["tags"] = [
        {"id": "t1", "label": "original", "type": "domain", "weight": 1.0, "created_at": "t0"}
    ]
    local = _empty_bundle("a", "t1")
    local["records"]["tags"] = [
        {"id": "t1", "label": "local-version", "type": "domain", "weight": 1.0,
         "created_at": "t0", "updated_at": "t1"}
    ]
    remote = _empty_bundle("b", "t2")
    remote["records"]["tags"] = [
        {"id": "t1", "label": "remote-version", "type": "domain", "weight": 1.0,
         "created_at": "t0", "updated_at": "t2"}
    ]
    result = three_way_merge(base, local, remote)
    tags = result.merged_bundle["records"]["tags"]
    assert len(tags) == 1
    assert tags[0]["label"] == "remote-version"


def test_merge_cascade_deletion_propagation():
    """cascade: base 存在, local+remote 都没有 → 删除."""
    base = _empty_bundle()
    base["records"]["tags"] = [
        {"id": "t1", "label": "Doomed", "type": "domain", "weight": 1.0, "created_at": "t0"}
    ]
    local = _empty_bundle("a", "t1")
    local["records"]["tags"] = []
    remote = _empty_bundle("b", "t1")
    remote["records"]["tags"] = []
    result = three_way_merge(base, local, remote)
    assert result.merged_bundle["records"]["tags"] == []


def test_merge_hotspot_tags_cascade():
    """hotspot_tags 按 (hotspot_id, tag_id) 复合键 cascade 合并."""
    base = _empty_bundle()
    local = _empty_bundle("a", "t1")
    local["records"]["hotspot_tags"] = [
        {"hotspot_id": "h1", "tag_id": "t1", "confidence": 0.8, "created_at": "t0"}
    ]
    remote = _empty_bundle("b", "t1")
    remote["records"]["hotspot_tags"] = [
        {"hotspot_id": "h1", "tag_id": "t2", "confidence": 0.9, "created_at": "t0"}
    ]
    result = three_way_merge(base, local, remote)
    pairs = {(ht["hotspot_id"], ht["tag_id"])
             for ht in result.merged_bundle["records"]["hotspot_tags"]}
    assert pairs == {("h1", "t1"), ("h1", "t2")}


# ---------------------------------------------------------------------------
# sm2_reviews — 特殊规则: due_at 早者胜出
# ---------------------------------------------------------------------------
def test_merge_sm2_local_due_earlier_wins():
    """sm2: local.due_at < remote.due_at → local 胜出。"""
    base = _empty_bundle()
    base["records"]["sm2_reviews"] = [
        {"id": "knowledge-k1", "entity_type": "knowledge", "entity_id": "k1",
         "easiness": 2.5, "interval": 0, "repetitions": 0,
         "due_at": "2026-08-01T00:00:00+00:00", "last_grade": 0,
         "last_reviewed_at": None, "created_at": "t0", "updated_at": "t0"}
    ]
    local = _empty_bundle("a", "t1")
    local["records"]["sm2_reviews"] = [
        {"id": "knowledge-k1", "entity_type": "knowledge", "entity_id": "k1",
         "easiness": 2.3, "interval": 1, "repetitions": 1,
         "due_at": "2026-07-25T00:00:00+00:00", "last_grade": 3,
         "last_reviewed_at": "2026-07-25", "created_at": "t0", "updated_at": "t1"}
    ]
    remote = _empty_bundle("b", "t2")
    remote["records"]["sm2_reviews"] = [
        {"id": "knowledge-k1", "entity_type": "knowledge", "entity_id": "k1",
         "easiness": 2.5, "interval": 6, "repetitions": 2,
         "due_at": "2026-08-15T00:00:00+00:00", "last_grade": 5,
         "last_reviewed_at": "2026-07-26", "created_at": "t0", "updated_at": "t2"}
    ]
    result = three_way_merge(base, local, remote)
    sm2 = result.merged_bundle["records"]["sm2_reviews"]
    assert len(sm2) == 1
    # local due_at (07-25) < remote due_at (08-15) → local 胜
    assert sm2[0]["due_at"] == "2026-07-25T00:00:00+00:00"
    assert sm2[0]["last_grade"] == 3
    assert sm2[0]["interval"] == 1


def test_merge_sm2_remote_due_earlier_wins():
    """sm2: remote.due_at < local.due_at → remote 胜出。"""
    base = _empty_bundle()
    base["records"]["sm2_reviews"] = [
        {"id": "knowledge-k2", "entity_type": "knowledge", "entity_id": "k2",
         "easiness": 2.5, "interval": 0, "repetitions": 0,
         "due_at": "2026-08-01T00:00:00+00:00", "last_grade": 0,
         "last_reviewed_at": None, "created_at": "t0", "updated_at": "t0"}
    ]
    local = _empty_bundle("a", "t1")
    local["records"]["sm2_reviews"] = [
        {"id": "knowledge-k2", "entity_type": "knowledge", "entity_id": "k2",
         "easiness": 2.5, "interval": 6, "repetitions": 2,
         "due_at": "2026-08-20T00:00:00+00:00", "last_grade": 5,
         "last_reviewed_at": "2026-07-26", "created_at": "t0", "updated_at": "t1"}
    ]
    remote = _empty_bundle("b", "t2")
    remote["records"]["sm2_reviews"] = [
        {"id": "knowledge-k2", "entity_type": "knowledge", "entity_id": "k2",
         "easiness": 2.3, "interval": 1, "repetitions": 1,
         "due_at": "2026-07-25T00:00:00+00:00", "last_grade": 3,
         "last_reviewed_at": "2026-07-25", "created_at": "t0", "updated_at": "t2"}
    ]
    result = three_way_merge(base, local, remote)
    sm2 = result.merged_bundle["records"]["sm2_reviews"]
    assert sm2[0]["due_at"] == "2026-07-25T00:00:00+00:00"


def test_merge_sm2_deletion_propagation():
    """sm2: base 存在, local+remote 都没有 → 删除."""
    base = _empty_bundle()
    base["records"]["sm2_reviews"] = [
        {"id": "knowledge-k3", "entity_type": "knowledge", "entity_id": "k3",
         "easiness": 2.5, "interval": 0, "repetitions": 0,
         "due_at": "2026-08-01T00:00:00+00:00", "last_grade": 0,
         "last_reviewed_at": None, "created_at": "t0", "updated_at": "t0"}
    ]
    local = _empty_bundle("a", "t1")
    local["records"]["sm2_reviews"] = []
    remote = _empty_bundle("b", "t1")
    remote["records"]["sm2_reviews"] = []
    result = three_way_merge(base, local, remote)
    assert result.merged_bundle["records"]["sm2_reviews"] == []


# ---------------------------------------------------------------------------
# 端到端 build/apply (通过 SQL 直接验证)
# ---------------------------------------------------------------------------
def test_build_bundle_includes_v17_tables(db):
    """build_bundle 包含 v1.7 5 个新表 keys."""
    from backend.services.sync_bundle import build_bundle
    bundle = build_bundle()
    records = bundle["records"]
    for key in ("tags", "hotspot_tags", "reading_states", "annotations", "sm2_reviews"):
        assert key in records, f"missing v1.7 key: {key}"
        assert isinstance(records[key], list), f"v1.7 key {key} not a list"


def test_apply_bundle_writes_sm2_with_due_at_guard(db):
    """apply_bundle: sm2 写入遵守 due_at 早者胜出约束 (远端 due_at 较晚则不覆盖)."""
    from datetime import datetime, timezone
    from backend.services.sync_bundle import apply_bundle

    now = datetime.now(timezone.utc).isoformat()
    early = "2026-07-25T00:00:00+00:00"
    late = "2026-08-15T00:00:00+00:00"

    # 先写入本地 (较早 due_at)
    bundle1 = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": now,
        "records": {
            "sm2_reviews": [
                {"id": "knowledge-k1", "entity_type": "knowledge", "entity_id": "k1",
                 "easiness": 2.3, "interval": 1, "repetitions": 1,
                 "due_at": early, "last_grade": 3, "last_reviewed_at": early,
                 "created_at": now, "updated_at": now}
            ],
        },
    }
    stats = apply_bundle(bundle1)
    assert stats["sm2_reviews"]["upserted"] == 1

    # 远端推送较晚 due_at → 不应覆盖本地 (due_at 早者胜)
    bundle2 = {
        "version": BUNDLE_VERSION, "device_id": "b", "merged_at": now,
        "records": {
            "sm2_reviews": [
                {"id": "knowledge-k1", "entity_type": "knowledge", "entity_id": "k1",
                 "easiness": 2.5, "interval": 6, "repetitions": 2,
                 "due_at": late, "last_grade": 5, "last_reviewed_at": late,
                 "created_at": now, "updated_at": now}
            ],
        },
    }
    apply_bundle(bundle2)
    row = _conn().execute(
        "SELECT * FROM sm2_reviews WHERE id=?", ("knowledge-k1",)
    ).fetchone()
    # early due_at 保留
    assert row["due_at"] == early
    assert row["easiness"] == 2.3


def test_apply_bundle_writes_reading_states_last_writer_wins(db):
    """apply_bundle: reading_states 远端 updated_at 较新则覆盖."""
    from datetime import datetime, timezone
    from backend.services.sync_bundle import apply_bundle

    now = datetime.now(timezone.utc).isoformat()
    # 本地先写入 (updated_at=t0)
    bundle1 = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": now,
        "records": {
            "reading_states": [
                {"entity_type": "hotspot", "entity_id": "h1",
                 "opened_count": 1, "dwell_ms": 100,
                 "last_read_at": "t0", "created_at": "t0", "updated_at": "t0"}
            ],
        },
    }
    apply_bundle(bundle1)
    # 远端推送 updated_at=t2 → 覆盖
    bundle2 = {
        "version": BUNDLE_VERSION, "device_id": "b", "merged_at": now,
        "records": {
            "reading_states": [
                {"entity_type": "hotspot", "entity_id": "h1",
                 "opened_count": 5, "dwell_ms": 500,
                 "last_read_at": "t2", "created_at": "t0", "updated_at": "t2"}
            ],
        },
    }
    apply_bundle(bundle2)
    row = _conn().execute(
        "SELECT * FROM reading_states WHERE entity_type=? AND entity_id=?",
        ("hotspot", "h1"),
    ).fetchone()
    assert row["opened_count"] == 5
    assert row["dwell_ms"] == 500


def test_apply_bundle_writes_tags_and_hotspot_tags(db):
    """apply_bundle: tags + hotspot_tags cascade 写入。"""
    from datetime import datetime, timezone
    from backend.services.sync_bundle import apply_bundle

    now = datetime.now(timezone.utc).isoformat()
    # hotspot_tags 引用 hotspots(id), 需要先插入 hotspot
    _conn().execute(
        """INSERT INTO hotspots (id, title, source, category, url,
                                 published_at, fetched_at)
           VALUES ('h1', 'Test Hotspot', 'rss', 'ai', 'https://example.com/h1',
                   ?, ?)""",
        (now, now),
    )
    _conn().commit()
    bundle = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": now,
        "records": {
            "tags": [
                {"id": "ai-security", "label": "AI安全", "type": "domain",
                 "weight": 1.5, "created_at": now}
            ],
            "hotspot_tags": [
                {"hotspot_id": "h1", "tag_id": "ai-security",
                 "confidence": 0.9, "created_at": now}
            ],
        },
    }
    stats = apply_bundle(bundle)
    assert stats["tags"]["tags_upserted"] == 1
    assert stats["tags"]["hotspot_tags_upserted"] == 1
    tag = _conn().execute(
        "SELECT * FROM tags WHERE id=?", ("ai-security",)
    ).fetchone()
    assert tag["label"] == "AI安全"
    ht = _conn().execute(
        "SELECT * FROM hotspot_tags WHERE hotspot_id=? AND tag_id=?",
        ("h1", "ai-security"),
    ).fetchone()
    assert ht["confidence"] == 0.9


def test_apply_bundle_writes_annotations(db):
    """apply_bundle: annotations last_writer_wins 写入。"""
    from datetime import datetime, timezone
    from backend.services.sync_bundle import apply_bundle

    now = datetime.now(timezone.utc).isoformat()
    bundle = {
        "version": BUNDLE_VERSION, "device_id": "a", "merged_at": now,
        "records": {
            "annotations": [
                {"id": "an-001", "entity_type": "knowledge", "entity_id": "k1",
                 "content": "重要观点", "range_start": 10, "range_end": 50,
                 "created_at": now, "updated_at": now}
            ],
        },
    }
    stats = apply_bundle(bundle)
    assert stats["annotations"]["upserted"] == 1
    row = _conn().execute(
        "SELECT * FROM annotations WHERE id=?", ("an-001",)
    ).fetchone()
    assert row["content"] == "重要观点"
    assert row["range_start"] == 10


# ---------------------------------------------------------------------------
# _merge_cascade / _merge_sm2_reviews 单元测试 (无 DB)
# ---------------------------------------------------------------------------
def test_cascade_helper_basic():
    """_merge_cascade: union + 删除信号。"""
    base = [{"id": "t1", "label": "L1"}]
    local = [{"id": "t1", "label": "L1"}, {"id": "t2", "label": "L2"}]
    remote = [{"id": "t3", "label": "R3"}]
    merged, conflicts = _merge_cascade(
        base, local, remote, lambda r: r["id"]
    )
    assert len(merged) == 3
    assert conflicts == 0


def test_cascade_helper_deletion():
    """_merge_cascade: base 存在但 local+remote 都没 → 删除。"""
    base = [{"id": "t1", "label": "L1"}]
    local = []
    remote = []
    merged, _ = _merge_cascade(base, local, remote, lambda r: r["id"])
    assert merged == []


def test_sm2_helper_earlier_due_wins():
    """_merge_sm2_reviews: due_at 早者胜出。"""
    base = []
    local = [{"id": "k1", "entity_type": "knowledge", "entity_id": "k1",
              "due_at": "2026-07-25T00:00:00+00:00", "easiness": 2.3}]
    remote = [{"id": "k1", "entity_type": "knowledge", "entity_id": "k1",
               "due_at": "2026-08-15T00:00:00+00:00", "easiness": 2.5}]
    merged, conflicts = _merge_sm2_reviews(base, local, remote)
    assert len(merged) == 1
    assert merged[0]["due_at"] == "2026-07-25T00:00:00+00:00"
    assert merged[0]["easiness"] == 2.3
    assert conflicts == 1

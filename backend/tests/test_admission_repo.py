"""admission_repo 单测 (R2 收缩批 — admission 四表写路径唯一化).

覆盖四表 repo 方法的关键语义 (业务编排由 service 层测试覆盖, 见
test_v1_admission_service.py / test_admission_log_service.py — repo 下沉后
那些用例逐字保留, 本文件只补 repo 自身的直测):

  1. admission_log INSERT 往返 (字段逐字 + matched_rule_id 可空)
  2. admission_label INSERT 往返 + DB CHECK (confidence 0.0-1.0)
  3. admission_set INSERT (item_count 字面量 0) + name UNIQUE
  4. find_set 存在 / 缺失分支
  5. admission_set_items INSERT OR IGNORE 幂等 (rowcount 1 → 0)
  6. refresh_set_item_count = COUNT(DISTINCT material_id)
  7. list_set_items JOIN + ORDER BY (material_id, dimension) + 键名
  8. repo 不吞 OperationalError (表缺失兜底归 service)
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.repository.admission_repo import AdmissionRepository
from backend.repository.db import get_connection

CREATED = "2026-01-01T00:00:00+00:00"

SAMPLE_DIM = {
    "entity_type": "cve",
    "confidence": "verified",
    "urgency": "immediate",
    "domain": "security",
    "impact": "high",
    "severity": "exploitable",
    "audience": "sec_team",
    "actionability": "actionable_now",
}


@pytest.fixture()
def repo(temp_db) -> AdmissionRepository:  # temp_db 只为建表 (migration 097)
    return AdmissionRepository()


# ---------------------------------------------------------------------------
# admission_log
# ---------------------------------------------------------------------------
def test_insert_log_roundtrip(repo) -> None:
    conn = get_connection()
    row_id = repo.insert_log(
        material_id="MAT-L1",
        body_hash="a" * 64,
        verdict="deny",
        reason="deny by rule",
        matched_rule_id=42,
        raw_material_json='{"id": "MAT-L1"}',
        created_at=CREATED,
    )
    conn.commit()
    assert row_id > 0
    row = conn.execute(
        "SELECT material_id, body_hash, verdict, reason, matched_rule_id, "
        "raw_material_json, created_at FROM admission_log WHERE id = ?",
        (row_id,),
    ).fetchone()
    assert tuple(row) == (
        "MAT-L1", "a" * 64, "deny", "deny by rule", 42, '{"id": "MAT-L1"}', CREATED,
    )


def test_insert_log_matched_rule_nullable(repo) -> None:
    """NEUTRAL / 无规则命中 → matched_rule_id 落 NULL (migration 097 语义)."""
    conn = get_connection()
    row_id = repo.insert_log(
        material_id="MAT-N1", body_hash="b" * 64, verdict="neutral",
        reason="no rule matched", matched_rule_id=None,
        raw_material_json="{}", created_at=CREATED,
    )
    conn.commit()
    row = conn.execute(
        "SELECT verdict, matched_rule_id FROM admission_log WHERE id = ?", (row_id,),
    ).fetchone()
    assert row[0] == "neutral" and row[1] is None


# ---------------------------------------------------------------------------
# admission_label
# ---------------------------------------------------------------------------
def test_insert_label_roundtrip(repo) -> None:
    conn = get_connection()
    label_id = repo.insert_label("MAT-LB1", "urgency", "watch", "human:t07", 0.85, CREATED)
    conn.commit()
    assert label_id > 0
    row = conn.execute(
        "SELECT material_id, dimension, value, annotator, confidence, created_at "
        "FROM admission_label WHERE id = ?",
        (label_id,),
    ).fetchone()
    assert tuple(row) == ("MAT-LB1", "urgency", "watch", "human:t07", 0.85, CREATED)


def test_insert_label_confidence_check_enforced(repo) -> None:
    """DB CHECK (confidence BETWEEN 0.0 AND 1.0) — repo 不拦截, 由库兜底."""
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_label("MAT-BAD", "impact", "high", "human:x", 1.5, CREATED)


# ---------------------------------------------------------------------------
# admission_set
# ---------------------------------------------------------------------------
def test_insert_set_literal_zero_count_and_unique_name(repo) -> None:
    conn = get_connection()
    set_id = repo.insert_set("r2-repo-set", "v1.0", CREATED)
    conn.commit()
    assert set_id > 0
    row = conn.execute(
        "SELECT name, schema_version, item_count, created_at FROM admission_set WHERE id = ?",
        (set_id,),
    ).fetchone()
    assert tuple(row) == ("r2-repo-set", "v1.0", 0, CREATED)
    # name UNIQUE: 重复创建 → IntegrityError (原语义: service 不捕获, 原样上抛)
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_set("r2-repo-set", "v1.0", CREATED)


def test_find_set_missing_returns_none(repo) -> None:
    assert repo.find_set(999999) is None
    set_id = repo.insert_set("find-set", "v1.0", CREATED)
    get_connection().commit()
    assert repo.find_set(set_id) is not None


# ---------------------------------------------------------------------------
# admission_set_items + 计数
# ---------------------------------------------------------------------------
def test_insert_set_item_idempotent_ignore(repo) -> None:
    """PK 冲突 → INSERT OR IGNORE 幂等命中, rowcount 1 → 0."""
    set_id = repo.insert_set("idem-set", "v1.0", CREATED)
    lid = repo.insert_label("MAT-I1", "domain", "ai", "set:x", 0.9, CREATED)
    get_connection().commit()
    assert repo.insert_set_item(set_id, "MAT-I1", lid) == 1
    assert repo.insert_set_item(set_id, "MAT-I1", lid) == 0


def test_refresh_set_item_count_distinct_materials(repo) -> None:
    """item_count = COUNT(DISTINCT material_id), 非 label 行数."""
    set_id = repo.insert_set("count-set", "v1.0", CREATED)
    l1 = repo.insert_label("MAT-C1", "domain", "ai", "set:x", 0.9, CREATED)
    l2 = repo.insert_label("MAT-C1", "impact", "high", "set:x", 0.9, CREATED)
    l3 = repo.insert_label("MAT-C2", "domain", "security", "set:x", 0.9, CREATED)
    for lid in (l1, l2, l3):
        repo.insert_set_item(set_id, "MAT-C1" if lid in (l1, l2) else "MAT-C2", lid)
    repo.refresh_set_item_count(set_id)
    get_connection().commit()
    row = get_connection().execute(
        "SELECT item_count FROM admission_set WHERE id = ?", (set_id,),
    ).fetchone()
    assert row[0] == 2  # 3 行 label, 2 个 distinct material


# ---------------------------------------------------------------------------
# list_set_items (JOIN 查询)
# ---------------------------------------------------------------------------
def test_list_set_items_join_order_and_keys(repo) -> None:
    set_id = repo.insert_set("join-set", "v1.0", CREATED)
    # 故意乱序插入: MAT-B/impact 先于 MAT-A/domain, 验证 ORDER BY 双键
    repo.insert_label("MAT-B", "impact", "high", "human:x", 0.9, CREATED)
    repo.insert_label("MAT-A", "domain", "ai", "human:x", 0.9, CREATED)
    get_connection().commit()
    b_lid = get_connection().execute(
        "SELECT id FROM admission_label WHERE material_id = 'MAT-B'", (),
    ).fetchone()[0]
    a_lid = get_connection().execute(
        "SELECT id FROM admission_label WHERE material_id = 'MAT-A'", (),
    ).fetchone()[0]
    repo.insert_set_item(set_id, "MAT-B", b_lid)
    repo.insert_set_item(set_id, "MAT-A", a_lid)
    get_connection().commit()

    items = repo.list_set_items(set_id)
    assert [(i["material_id"], i["dimension"]) for i in items] == [
        ("MAT-A", "domain"),
        ("MAT-B", "impact"),
    ]
    assert set(items[0].keys()) == {
        "set_id", "material_id", "label_id", "dimension",
        "value", "annotator", "confidence", "created_at",
    }
    assert items[0]["set_id"] == set_id and items[0]["value"] == "ai"


# ---------------------------------------------------------------------------
# 边界: repo 不吞 OperationalError (表缺失兜底语义归 service)
# ---------------------------------------------------------------------------
def test_missing_table_raises_operational_error() -> None:
    """注入无表的 :memory: 连接 → OperationalError 原样上抛, 不静默返 0."""
    mem = sqlite3.connect(":memory:")
    try:
        bare = AdmissionRepository(mem)
        with pytest.raises(sqlite3.OperationalError):
            bare.insert_log("MAT-X", "h", "deny", "r", None, "{}", CREATED)
        with pytest.raises(sqlite3.OperationalError):
            bare.list_set_items(1)
    finally:
        mem.close()

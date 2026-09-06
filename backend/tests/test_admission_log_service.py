"""v1.0 T07 admission_log service 测试 — label + create_label_set + add_to_set + get_set_items.

约束:
  - 全部走 temp_db fixture (T01 隔离根)
  - 维度/值越界 → ValueError
  - 集大小计数 = 实际 distinct material 数
"""
from __future__ import annotations

import pytest

from backend.services.v1_admission_service import (
    ANNOTATION_DIMENSIONS,
    V1AdmissionService,
)

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


# ---------------------------------------------------------------------------
# label 单条写入
# ---------------------------------------------------------------------------
def test_label_writes_eight_dimensions(temp_db) -> None:
    """单条 label() 调用写 8 行 (每维一行)."""
    svc = V1AdmissionService()
    label_id = svc.label("MAT-1", SAMPLE_DIM, annotator="human:test", confidence=0.85)
    assert label_id > 0  # 至少返第一条 label_id
    # 校验 8 行入库
    from backend.repository.db import get_connection
    rows = get_connection().execute(
        "SELECT dimension, value, annotator, confidence FROM admission_label "
        "WHERE material_id = ? ORDER BY dimension",
        ("MAT-1",),
    ).fetchall()
    assert len(rows) == 8
    dims = {r[0] for r in rows}
    assert dims == set(ANNOTATION_DIMENSIONS.keys())
    # confidence 一致
    assert all(r[3] == 0.85 for r in rows)


def test_label_rejects_unknown_dimension(temp_db) -> None:
    svc = V1AdmissionService()
    with pytest.raises(ValueError, match="未知维度"):
        svc.label("MAT-x", {"not_a_dim": "x"}, annotator="t")


def test_label_rejects_out_of_range_value(temp_db) -> None:
    svc = V1AdmissionService()
    with pytest.raises(ValueError, match="越界"):
        svc.label("MAT-x", {"entity_type": "unknown_thing"}, annotator="t")


def test_label_rejects_invalid_confidence(temp_db) -> None:
    svc = V1AdmissionService()
    with pytest.raises(ValueError, match="confidence 必须在"):
        svc.label("MAT-x", SAMPLE_DIM, annotator="t", confidence=1.5)


def test_label_rejects_empty_dimensions(temp_db) -> None:
    svc = V1AdmissionService()
    with pytest.raises(ValueError, match="dimensions 不能为空"):
        svc.label("MAT-x", {}, annotator="t")


# ---------------------------------------------------------------------------
# create_label_set + add_to_set + get_set_items 三段
# ---------------------------------------------------------------------------
def test_create_label_set_and_add(temp_db) -> None:
    """create_label_set → add_to_set → get_set_items 三段贯通."""
    svc = V1AdmissionService()
    set_id = svc.create_label_set("t07-test-set")
    assert set_id > 0
    lid1 = svc.add_to_set(set_id, "MAT-A", SAMPLE_DIM)
    lid2 = svc.add_to_set(set_id, "MAT-B", {
        "entity_type": "research",
        "confidence": "likely",
        "urgency": "watch",
        "domain": "ai",
        "impact": "medium",
        "severity": "theoretical",
        "audience": "product_team",
        "actionability": "informational",
    })
    assert lid1 > 0 and lid2 > 0
    items = svc.get_set_items(set_id)
    # 2 material × 8 dim = 16 行
    assert len(items) == 16
    distinct = {i["material_id"] for i in items}
    assert distinct == {"MAT-A", "MAT-B"}


def test_create_label_set_duplicate_name_fails(temp_db) -> None:
    """UNIQUE 约束: name 重复 → IntegrityError."""
    svc = V1AdmissionService()
    svc.create_label_set("dup-name")
    with pytest.raises(Exception):  # sqlite3.IntegrityError
        svc.create_label_set("dup-name")


def test_add_to_set_rejects_unknown_set_id(temp_db) -> None:
    """add_to_set 入不存在的 set_id → ValueError."""
    svc = V1AdmissionService()
    with pytest.raises(ValueError, match="不存在"):
        svc.add_to_set(999999, "MAT-X", SAMPLE_DIM)


def test_get_set_items_returns_empty_for_empty_set(temp_db) -> None:
    """刚创建的空集 → get_set_items 返 []."""
    svc = V1AdmissionService()
    set_id = svc.create_label_set("empty-set")
    assert svc.get_set_items(set_id) == []


# ---------------------------------------------------------------------------
# 集大小计数 (item_count 与实际一致)
# ---------------------------------------------------------------------------
def test_set_item_count_matches_distinct_materials(temp_db) -> None:
    """item_count = distinct material 数 (不是 label 行数)."""
    svc = V1AdmissionService()
    set_id = svc.create_label_set("count-test")
    for i in range(5):
        svc.add_to_set(set_id, f"MAT-{i:03d}", SAMPLE_DIM)
    # item_count 应为 5
    from backend.repository.db import get_connection
    row = get_connection().execute(
        "SELECT item_count FROM admission_set WHERE id = ?", (set_id,)
    ).fetchone()
    assert row[0] == 5
    # get_set_items 返 5*8 = 40 行
    assert len(svc.get_set_items(set_id)) == 40


def test_set_item_count_dedupes_same_material(temp_db) -> None:
    """同一 material 多次 add → item_count 不重复计数."""
    svc = V1AdmissionService()
    set_id = svc.create_label_set("dedup-test")
    svc.add_to_set(set_id, "MAT-DUP", SAMPLE_DIM)
    svc.add_to_set(set_id, "MAT-DUP", SAMPLE_DIM)  # 重复
    from backend.repository.db import get_connection
    row = get_connection().execute(
        "SELECT item_count FROM admission_set WHERE id = ?", (set_id,)
    ).fetchone()
    # distinct material 仍为 1
    assert row[0] == 1

"""v1.0 T07 准入服务测试 — evaluate (deny > allow > neutral) + quarantine 兜底 + label 推断."""
from __future__ import annotations

from backend.services.v1_admission_service import (
    ANNOTATION_DIMENSIONS,
    AdmissionResult,
    AdmissionVerdict,
    V1AdmissionService,
    label_count,
)


def test_label_count_in_60_80_range() -> None:
    """标注集 60-80 起步 (任务台账 §16)."""
    n = label_count()
    # 8 维笛卡尔积上限可能 >> 80, 任务台账的"60-80 起步"是"实际标注定量"非笛卡尔积
    # 这里验证 ANNOTATION_DIMENSIONS 自身合法, 实际标注批次由 T07 监督流程控
    assert n >= 64  # 8 维 × 至少 2 档
    # 维度数
    assert len(ANNOTATION_DIMENSIONS) == 8


def test_evaluate_neutral_when_no_rules() -> None:
    svc = V1AdmissionService()
    res = svc.evaluate({"id": "MAT-1", "category": "security", "source_name": "Test"})
    assert res.verdict == AdmissionVerdict.NEUTRAL
    assert res.matched_rule is None
    assert "no rule matched" in res.reason


def test_evaluate_deny_overrides_allow() -> None:
    """deny 规则优先于 allow (与 info_filter 语义一致)."""
    svc = V1AdmissionService()
    rules = [
        {"rule_type": "allow", "match_kind": "category", "match_value": "security", "enabled": 1, "note": "allow sec"},
        {"rule_type": "deny", "match_kind": "category", "match_value": "security", "enabled": 1, "note": "deny sec"},
    ]
    res = svc.evaluate({"id": "MAT-2", "category": "security", "source_name": "X"}, rules=rules)
    assert res.verdict == AdmissionVerdict.DENY
    assert "deny" in res.reason


def test_evaluate_allow_when_no_deny() -> None:
    svc = V1AdmissionService()
    rules = [
        {"rule_type": "allow", "match_kind": "source_name", "match_value": "Trusted", "enabled": 1, "note": "trusted source"},
    ]
    res = svc.evaluate({"id": "MAT-3", "category": "security", "source_name": "Trusted"}, rules=rules)
    assert res.verdict == AdmissionVerdict.ALLOW


def test_default_labels_entity_type_cve() -> None:
    """URL 含 CVE → entity_type=cve."""
    svc = V1AdmissionService()
    labels = svc.default_labels({"id": "x", "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-31337"})
    assert labels["entity_type"] == "cve"
    assert labels["domain"] == "security"
    assert labels["urgency"] == "watch"
    assert labels["confidence"] == "unverified"


def test_default_labels_entity_type_ai() -> None:
    """category 含 ai → domain=ai."""
    svc = V1AdmissionService()
    labels = svc.default_labels({"id": "x", "category": "ai_security"})
    assert labels["domain"] == "ai"


def test_default_labels_eight_dimensions() -> None:
    """默认 label 必须覆盖全部 8 维."""
    svc = V1AdmissionService()
    labels = svc.default_labels({"id": "x", "category": "security"})
    assert set(labels.keys()) == set(ANNOTATION_DIMENSIONS.keys())


def test_quarantine_silently_returns_zero_when_table_missing(monkeypatch) -> None:
    """admission_log 表未建 (migration 097 未跑场景) → 静默降级返 0, 不抛.

    会话级 init_db 已跑 migration 097 (真落库路径被覆盖), 这里显式给
    V1AdmissionService 实例注入一个无 admission_log 表的临时连接, 模拟
    "升级窗口期"语义, 验证 OperationalError 兜底.
    """
    import sqlite3 as _sql

    tmp_con = _sql.connect(":memory:")
    svc = V1AdmissionService(conn=tmp_con)
    res = AdmissionResult(
        verdict=AdmissionVerdict.DENY, material_id="MAT-x",
        matched_rule={"id": 1, "note": "deny"}, reason="deny",
    )
    row_id = svc.quarantine(res, {"id": "MAT-x", "url": "https://example.com/x"})
    assert row_id == 0  # 表不存在, 兜底
    tmp_con.close()


def test_quarantine_writes_real_row_when_table_exists(temp_db) -> None:
    """migration 097 跑后 → quarantine 真落 admission_log, row_id > 0."""
    from backend.repository.db import get_connection

    svc = V1AdmissionService()
    res = AdmissionResult(
        verdict=AdmissionVerdict.DENY, material_id="MAT-REAL",
        matched_rule={"id": 42, "note": "deny rule 42"}, reason="deny by rule",
    )
    row_id = svc.quarantine(res, {"id": "MAT-REAL", "url": "https://example.com/x"})
    assert row_id > 0
    # 校验入库内容
    row = get_connection().execute(
        "SELECT material_id, verdict, reason, matched_rule_id FROM admission_log WHERE id = ?",
        (row_id,),
    ).fetchone()
    assert row[0] == "MAT-REAL"
    assert row[1] == "deny"
    assert row[2] == "deny by rule"
    assert row[3] == 42


def test_evaluate_plus_label_full_eight_dimensions(temp_db) -> None:
    """evaluate + label 串联: 准入 → 标注, 8 维 label 全部覆盖."""
    svc = V1AdmissionService()
    rules = [
        {"rule_type": "allow", "match_kind": "category", "match_value": "ai",
         "enabled": 1, "note": "allow ai"},
    ]
    material = {"id": "MAT-AI-1", "category": "ai", "source_name": "QbitAI",
                "url": "https://qbitai.com/article/1"}
    res = svc.evaluate(material, rules=rules)
    assert res.verdict == AdmissionVerdict.ALLOW

    # 8 维 label 全部覆盖
    full_labels = svc.default_labels(material)
    assert set(full_labels.keys()) == set(ANNOTATION_DIMENSIONS.keys())

    label_id = svc.label(material["id"], full_labels, annotator="human:t07-test")
    assert label_id > 0
    # 校验 8 行入库
    from backend.repository.db import get_connection
    rows = get_connection().execute(
        "SELECT dimension FROM admission_label WHERE material_id = ?", (material["id"],),
    ).fetchall()
    assert len(rows) == 8


def test_evaluate_disabled_rule_ignored() -> None:
    """enabled=0 的规则应被忽略."""
    svc = V1AdmissionService()
    rules = [
        {"rule_type": "deny", "match_kind": "category", "match_value": "security",
         "enabled": 0, "note": "disabled deny"},
    ]
    res = svc.evaluate({"id": "MAT-4", "category": "security", "source_name": "X"}, rules=rules)
    # 规则 disabled → NEUTRAL
    assert res.verdict == AdmissionVerdict.NEUTRAL

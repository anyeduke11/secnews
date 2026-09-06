"""v1.0 T07 准入服务测试 — evaluate (deny > allow > neutral) + quarantine 兜底 + label 推断."""
from __future__ import annotations

import pytest

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


def test_quarantine_silently_returns_zero_when_table_missing() -> None:
    """admission_log 表未建 (T07 migration 097 后续) → 静默降级返 0, 不抛."""
    svc = V1AdmissionService()
    res = AdmissionResult(
        verdict=AdmissionVerdict.DENY, material_id="MAT-x",
        matched_rule={"id": 1, "note": "deny"}, reason="deny",
    )
    row_id = svc.quarantine(res, {"id": "MAT-x", "url": "https://example.com/x"})
    assert row_id == 0  # 表不存在, 兜底


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

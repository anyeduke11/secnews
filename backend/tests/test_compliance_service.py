"""S4-4 合规矩阵服务测试。"""
from __future__ import annotations

from backend.services.compliance_service import controls_for_event, list_frameworks, matrix


def test_list_frameworks_returns_three():
    fws = list_frameworks()
    assert len(fws) == 3
    ids = {fw["id"] for fw in fws}
    assert ids == {"dengbao", "gdpr", "iso27001"}


def test_controls_for_event_known_type():
    controls = controls_for_event("data_breach")
    assert len(controls) > 0
    frameworks = {c["framework"] for c in controls}
    assert "gdpr" in frameworks
    assert "dengbao" in frameworks


def test_controls_for_event_unknown_type():
    controls = controls_for_event("nonexistent_event_xyz")
    assert controls == []


def test_matrix_rows_and_columns():
    result = matrix(["data_breach", "unauthorized_access"])
    assert len(result["rows"]) == 2
    assert len(result["columns"]) > 0
    assert all("framework" in c and "control_id" in c for c in result["columns"])


def test_matrix_with_framework_filter():
    result = matrix(["data_breach"], frameworks=["gdpr"])
    assert all(c["framework"] == "gdpr" for c in result["columns"])
    for row in result["rows"]:
        assert all(c["framework"] == "gdpr" for c in row["controls"])


def test_matrix_empty_event_types():
    result = matrix([])
    assert result["rows"] == []
    assert result["columns"] == []


__all__ = [
    "test_controls_for_event_known_type",
    "test_controls_for_event_unknown_type",
    "test_list_frameworks_returns_three",
    "test_matrix_empty_event_types",
    "test_matrix_rows_and_columns",
    "test_matrix_with_framework_filter",
]

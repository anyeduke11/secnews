"""T12 SK-03 inspection_materials prompt 模板测试 (4 个)."""
from __future__ import annotations

import json

from backend.services.ai_hub.prompts import (
    INSPECTION_MATERIALS_SCHEMA_V1,
    build_inspection_materials_prompt,
    parse_inspection_materials_response,
)


def test_schema_v1_has_required_fields() -> None:
    """schema 含 plan/expected_artifacts/success_criteria/tool_versions/unknowns."""
    for k in ("plan", "expected_artifacts", "success_criteria", "tool_versions", "unknowns"):
        assert k in INSPECTION_MATERIALS_SCHEMA_V1


def test_prompt_includes_case_judgment_scope() -> None:
    """prompt 必含 case_id + judgment_id + subject + cve_id + scope + 纪律段."""
    materials = [
        {"id": "MAT-001", "title": "Advisory", "content_hash": "h" * 64, "summary": "RCE"},
    ]
    p = build_inspection_materials_prompt(
        case_id="CASE" + "X" * 22, judgment_id="JUDG" + "X" * 22,
        subject_name="某网关", cve_id="CVE-2026-31337", scope="生产",
        evidence_materials=materials,
    )
    assert "CASE" in p
    assert "JUDG" in p
    assert "某网关" in p
    assert "CVE-2026-31337" in p
    assert "MAT-001" in p
    assert "材料" in p
    assert "unknowns" in p


def test_parse_response_strips_code_fence() -> None:
    raw = (
        "```json\n"
        + json.dumps({
            "plan": "# Plan\n1. 升级",
            "expected_artifacts": ["checklist", "report"],
            "success_criteria": "升级完成 + 验证通过",
            "tool_versions": {"patcher": "1.0"},
            "unknowns": [],
        })
        + "\n```"
    )
    out = parse_inspection_materials_response(raw)
    assert out["plan"].startswith("# Plan")
    assert out["expected_artifacts"] == ["checklist", "report"]
    assert out["tool_versions"] == {"patcher": "1.0"}


def test_parse_response_rejects_empty_artifacts() -> None:
    """expected_artifacts 至少 1 条 (材料 ≠ 排查)."""
    bad = json.dumps({
        "plan": "x", "expected_artifacts": [], "success_criteria": "y",
        "tool_versions": {}, "unknowns": [],
    })
    try:
        parse_inspection_materials_response(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty expected_artifacts")

"""T11 SK-02 cve_impact_brief prompt 模板测试."""
from __future__ import annotations

import json

from backend.services.ai_hub.prompts import (
    CVE_IMPACT_BRIEF_SCHEMA_V1,
    build_cve_impact_brief_prompt,
    parse_cve_impact_brief_response,
)


def test_schema_v1_has_required_fields() -> None:
    """schema 含 claim/conditions/evidence_refs/unknowns/claim_type/confidence."""
    for k in ("claim_type", "claim", "conditions", "confidence", "evidence_refs", "counter_evidence_refs", "unknowns"):
        assert k in CVE_IMPACT_BRIEF_SCHEMA_V1


def test_prompt_includes_cve_id_and_subject() -> None:
    """prompt 必含 CVE ID + subject_name + evidence_materials + 纪律段."""
    materials = [
        {"id": "MAT-001", "title": "NVD entry", "content_hash": "h" * 64, "summary": "RCE in X"},
    ]
    p = build_cve_impact_brief_prompt(
        cve_id="CVE-2026-31337", subject_name="某 SSL VPN 网关", evidence_materials=materials,
    )
    assert "CVE-2026-31337" in p
    assert "某 SSL VPN 网关" in p
    assert "MAT-001" in p
    assert "未知项" in p  # 纪律段 (中文)
    assert "evidence_refs" in p  # JSON schema 段


def test_prompt_with_no_materials_emits_unknowns_discipline() -> None:
    """缺证据场景: prompt 显式提示 'unknowns 必填'."""
    p = build_cve_impact_brief_prompt(
        cve_id="CVE-2026-31337", subject_name="X", evidence_materials=[],
    )
    assert "无 materials" in p
    assert "unknowns" in p


def test_parse_response_strips_code_fence() -> None:
    """响应包 ```json ... ``` 时能剥掉."""
    raw = (
        '```json\n'
        + json.dumps({
            "claim_type": "finding", "claim": "X", "conditions": "Y",
            "confidence": "high", "evidence_refs": [], "unknowns": ["缺版本"],
        })
        + '\n```'
    )
    out = parse_cve_impact_brief_response(raw)
    assert out["claim_type"] == "finding"
    assert out["unknowns"] == ["缺版本"]


def test_parse_response_validates_claim_type_and_confidence() -> None:
    """claim_type/confidence 非法值抛 ValueError."""
    bad = json.dumps({
        "claim_type": "wrong", "claim": "X", "conditions": "",
        "confidence": "high", "evidence_refs": [], "unknowns": [],
    })
    try:
        parse_cve_impact_brief_response(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for bad claim_type")
    bad2 = json.dumps({
        "claim_type": "finding", "claim": "X", "conditions": "",
        "confidence": "extreme", "evidence_refs": [], "unknowns": [],
    })
    try:
        parse_cve_impact_brief_response(bad2)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for bad confidence")


def test_parse_response_empty_raises() -> None:
    try:
        parse_cve_impact_brief_response("")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty")

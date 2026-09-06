"""T13 SK-04 knowledge_publish prompt 模板测试 (4 个)."""
from __future__ import annotations

import json

from backend.services.ai_hub.prompts import (
    KNOWLEDGE_PUBLISH_SCHEMA_V1,
    build_knowledge_prompt,
    parse_knowledge_publish_response,
)


def test_schema_v1_has_required_fields() -> None:
    """schema 含 title/body/prerequisites/counter_examples/evidence_refs/review_at."""
    for k in ("title", "body", "prerequisites", "counter_examples", "evidence_refs", "review_at"):
        assert k in KNOWLEDGE_PUBLISH_SCHEMA_V1


def test_prompt_includes_case_judgment_action_kind() -> None:
    """prompt 必含 case_id + judgment_id + action_id + subject + cve + kind + 纪律."""
    materials = [{"id": "MAT-001", "title": "T", "content_hash": "h" * 64, "summary": "x"}]
    p = build_knowledge_prompt(
        case_id="C" * 26, judgment_id="J" * 26, action_id="A" * 26,
        subject_name="网关", cve_id="CVE-2026-31337", kind="playbook",
        evidence_materials=materials,
    )
    assert "C" * 26 in p
    assert "J" * 26 in p
    assert "A" * 26 in p
    assert "网关" in p
    assert "CVE-2026-31337" in p
    assert "playbook" in p
    assert "MAT-001" in p
    assert "review_at" in p
    assert "prerequisites" in p


def test_parse_response_strips_code_fence() -> None:
    raw = (
        "```json\n"
        + json.dumps({
            "title": "K1", "body": "# K\n1. step",
            "prerequisites": ["FastGate 7.2.0+"],
            "counter_examples": ["不适用内网部署"],
            "evidence_refs": [{"material_id": "MAT-001", "hash": "h" * 64, "quote": "ok"}],
            "review_at": "2026-12-01T00:00:00+00:00",
        })
        + "\n```"
    )
    out = parse_knowledge_publish_response(raw)
    assert out["title"] == "K1"
    assert out["prerequisites"] == ["FastGate 7.2.0+"]
    assert out["review_at"] == "2026-12-01T00:00:00+00:00"


def test_parse_response_rejects_missing_prerequisites() -> None:
    """SK-04 硬约束: prerequisites ≥ 1."""
    bad = json.dumps({
        "title": "K1", "body": "x", "prerequisites": [],
        "counter_examples": [], "evidence_refs": [{"material_id": "M", "hash": "h" * 64}],
        "review_at": "2026-12-01T00:00:00+00:00",
    })
    try:
        parse_knowledge_publish_response(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty prerequisites")


def test_parse_response_rejects_missing_review_at() -> None:
    """SK-06 触发: review_at 必填."""
    bad = json.dumps({
        "title": "K1", "body": "x", "prerequisites": ["p"],
        "counter_examples": [], "evidence_refs": [{"material_id": "M", "hash": "h" * 64}],
    })
    try:
        parse_knowledge_publish_response(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for missing review_at")

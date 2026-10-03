"""judgment_drafter 纯函数测试 — JSON 容错解析/必填校验/md 渲染。

WHY (Rule 9): 模型输出不可信 — 围栏 JSON、前后缀文字、缺 claim、confidence
非法值都必须显式失败 (不编造), 这些分支是"AI 失败不伪造"纪律的落点。
"""
from __future__ import annotations

import pytest

from backend.services.judgment_drafter import (
    JUDGMENT_DRAFT_PROMPT_VERSION,
    JudgmentDraftError,
    _coerce_payload,
    _parse_json_object,
    render_judgment_markdown,
)


def test_parse_plain_json_object():
    assert _parse_json_object('{"claim": "x", "confidence": "high"}')["claim"] == "x"


def test_parse_json_inside_fence():
    raw = '前缀文字\n```json\n{"claim": "x", "confidence": "low"}\n```\n后缀'
    assert _parse_json_object(raw)["confidence"] == "low"


def test_parse_rejects_non_object():
    with pytest.raises(JudgmentDraftError, match="not an object"):
        _parse_json_object('["a", "b"]')


def test_parse_rejects_garbage():
    with pytest.raises(JudgmentDraftError, match="not valid JSON"):
        _parse_json_object("模型拒绝回答")


def test_coerce_requires_claim():
    with pytest.raises(JudgmentDraftError, match="claim"):
        _coerce_payload({"confidence": "high"})


def test_coerce_rejects_bad_confidence():
    with pytest.raises(JudgmentDraftError, match="confidence invalid"):
        _coerce_payload({"claim": "x", "confidence": "maybe"})


def test_coerce_normalizes_unknowns_to_clean_strings():
    out = _coerce_payload({
        "claim": "x", "confidence": "medium",
        "unknowns": [" a ", 123, "", None],
    })
    assert out["unknowns"] == ["a", "123"]
    assert out["conditions"] == ""


def test_render_includes_source_urls_and_provenance():
    md = render_judgment_markdown(
        case_id="case_X",
        payload={"claim": "可利用", "conditions": "边界暴露",
                 "confidence": "high", "unknowns": ["内网拓扑"]},
        evidence=[{"id": "mat_1", "title": "公告",
                   "url": "https://src.example.com/cve/1",
                   "content_hash": "abcd" + "0" * 60}],
        proposal_id="prop_ABC",
    )
    assert "可利用" in md
    assert "https://src.example.com/cve/1" in md  # 回溯终端: Source 原文
    assert "prop_ABC" in md
    assert JUDGMENT_DRAFT_PROMPT_VERSION in md
    assert "sha256:abcd" in md

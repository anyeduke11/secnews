# backend/tests/test_pipeline_llm_gates.py
"""管线 LLM 三 gate (semantic_filter / ai_classify / pipeline_ner) 登记与默认态。

契约 (user_skills 先例): gate 化须随消费点同时登记 — 不登记则 TOML/env
同名 key 被 _load_gates 过滤, is_extension_enabled 恒 False (fail-closed)。
"""
import os

import pytest

from backend.extensions import _EXTENSION_NAMES, is_extension_enabled, reset_gates

PIPELINE_GATES = ("semantic_filter", "ai_classify", "pipeline_ner")


def test_three_gates_registered():
    for name in PIPELINE_GATES:
        assert name in _EXTENSION_NAMES, f"{name} 未登记 — TOML 键会被过滤恒 False"


def test_default_off_in_toml(monkeypatch):
    """生产默认关: 不设 env 时三 gate 读 TOML false。"""
    monkeypatch.delenv("HOTSPOT_FEATURE_GATES", raising=False)
    reset_gates()
    for name in PIPELINE_GATES:
        assert is_extension_enabled(name) is False
    reset_gates()


@pytest.mark.parametrize("gate", PIPELINE_GATES)
def test_env_override_on(monkeypatch, gate):
    monkeypatch.setenv(
        "HOTSPOT_FEATURE_GATES", f'{{"extensions": {{"{gate}": true}}}}'
    )
    reset_gates()
    assert is_extension_enabled(gate) is True
    reset_gates()

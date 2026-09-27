"""pi 主力化配置锚 (2026-09-27 owner 裁决) — 防 fallback 链回退漂移。

契约: pi 是 default_provider 且 fallback_order 首位; 既有四 provider 保留
为兜底 (spec §2.2: 降级不删除, 见 docs/superpowers/specs/2026-09-27-pi-primary-engine-design.md)。
锚定仓库内真实 config/llm.yaml, 防"改回 sensenova 主力而无人知晓"。
"""
from pathlib import Path

import yaml

from backend.config.llm_schema import LLMConfig

_REPO_LLM_YAML = Path(__file__).resolve().parents[2] / "config" / "llm.yaml"


def _load_repo_llm_yaml() -> LLMConfig:
    return LLMConfig.model_validate(yaml.safe_load(_REPO_LLM_YAML.read_text(encoding="utf-8")))


def test_pi_is_default_provider():
    assert _load_repo_llm_yaml().default_provider == "pi"


def test_pi_leads_fallback_order():
    order = _load_repo_llm_yaml().fallback_order
    assert order[0] == "pi"
    assert order[1] == "ollama"  # 本地零成本为第一兜底


def test_legacy_providers_kept_as_fallback():
    names = set(_load_repo_llm_yaml().providers)
    assert {"ollama", "sensenova", "qwen", "openai"} <= names

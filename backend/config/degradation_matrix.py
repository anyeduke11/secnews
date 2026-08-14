"""配置降级矩阵 — 5 种缺失配置场景的降级行为.

Phase 16 — Hybrid AI 配置降级管理。
"""
from __future__ import annotations

import logging
from pathlib import Path

from backend.config.llm_schema import LLMConfig, load_llm_config

logger = logging.getLogger("hotspot.degradation")

# 降级场景枚举
DEGRADATION_SCENARIOS = {
    "no_config": "No llm.yaml file found — running in v1.7 compatibility mode",
    "disabled": "LLM explicitly disabled (enabled: false) — v1.7 compatibility mode",
    "no_provider": "No LLM provider configured — T1/T3 will fail with 5xx errors",
    "ollama_only": "Only Ollama configured — T1/T3 use local LLM, T2/T4 require external Agent",
    "full": "All providers configured — local LLM primary, external Agent fallback",
}


class DegradationMatrix:
    """配置降级矩阵，检测当前 LLM 配置状态并确定降级级别."""

    def __init__(self, config: LLMConfig | None = None):
        self._config = config
        self._scenario = self._detect()

    def _detect(self) -> str:
        """检测当前降级场景."""
        if self._config is None:
            return "no_config"
        if not self._config.enabled:
            return "disabled"
        providers = self._config.providers or {}
        if not providers:
            return "no_provider"
        # 检查至少有一个 provider 有可用的模型
        has_ollama = "ollama" in providers
        has_api = any(
            p.api_key_env for name, p in providers.items() if name != "ollama"
        )
        if has_ollama and has_api:
            return "full"
        if has_ollama:
            return "ollama_only"
        if has_api:
            # 有 API key 但无 Ollama
            return "full"
        return "no_provider"

    @property
    def scenario(self) -> str:
        return self._scenario

    @property
    def description(self) -> str:
        return DEGRADATION_SCENARIOS.get(self._scenario, "Unknown")

    @property
    def requires_external_agent(self) -> bool:
        """是否需要外部 Agent 来执行 T1/T3."""
        return self._scenario in ("no_config", "disabled")

    @property
    def t1_available(self) -> bool:
        """T1 评分是否可用（本地或外部）. """
        return self._scenario not in ("no_provider",)

    @property
    def t3_available(self) -> bool:
        """T3 摘要是否可用."""
        return self._scenario not in ("no_provider",)

    def status(self) -> dict[str, object]:
        """返回当前降级状态 JSON."""
        return {
            "scenario": self._scenario,
            "description": self.description,
            "requires_external_agent": self.requires_external_agent,
            "t1_available": self.t1_available,
            "t3_available": self.t3_available,
            "llm_enabled": self._config is not None and self._config.enabled,
            "default_provider": (
                self._config.default_provider
                if self._config and self._config.enabled
                else None
            ),
            "fallback_order": (
                self._config.fallback_order
                if self._config and self._config.enabled
                else []
            ),
        }


def create_degradation_matrix(config_path: Path | None = None) -> DegradationMatrix:
    """从配置文件创建降级矩阵."""
    cfg = load_llm_config(config_path)
    matrix = DegradationMatrix(cfg)
    logger.info("Degradation scenario: %s — %s", matrix.scenario, matrix.description)
    return matrix


__all__ = [
    "DEGRADATION_SCENARIOS",
    "DegradationMatrix",
    "create_degradation_matrix",
]
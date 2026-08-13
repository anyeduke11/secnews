"""LLM 配置文件 schema 验证 (Pydantic).

Phase 16 — Hybrid AI 配置文件校验。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator


class ProviderModels(BaseModel):
    score: str = "qwen2.5:7b"
    tag: str = "qwen2.5:7b"
    ner: str = "qwen2.5:7b"
    summary: str = "qwen2.5:14b"
    chunk_summary: str = "qwen2.5:7b"


class ProviderConfig(BaseModel):
    type: Literal["ollama", "openai", "openai_compatible", "anthropic"]
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    models: ProviderModels
    timeout_seconds: int = 30
    max_concurrent: int = 4


class TaskOverride(BaseModel):
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 100
    batch_size: Optional[int] = None


class RateLimits(BaseModel):
    requests_per_minute: int = 60
    tokens_per_minute: int = 100000


class CostAlert(BaseModel):
    daily_usd_limit: float = 5.0
    monthly_usd_limit: float = 100.0
    on_exceeded: Literal["warn", "block", "fallback_local"] = "warn"


class CacheConfig(BaseModel):
    enabled: bool = True
    ttl_seconds: int = 86400
    similarity_threshold: float = 0.95


class LLMConfig(BaseModel):
    enabled: bool = True
    default_provider: str = "openai"
    fallback_order: List[str] = ["ollama", "qwen", "openai"]
    providers: Dict[str, ProviderConfig]
    task_overrides: Optional[Dict[str, TaskOverride]] = None
    rate_limits: RateLimits = RateLimits()
    cost_alert: CostAlert = CostAlert()
    cache: CacheConfig = CacheConfig()

    @model_validator(mode="after")
    def _validate_fallback_order(self) -> "LLMConfig":
        for p in self.fallback_order:
            if p not in self.providers:
                raise ValueError(f"fallback_order provider '{p}' not in providers")
        return self

    @model_validator(mode="after")
    def _validate_default_provider(self) -> "LLMConfig":
        if self.default_provider not in self.providers:
            raise ValueError(
                f"default_provider '{self.default_provider}' not in providers"
            )
        return self


_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "llm.yaml"


def load_llm_config(path: Optional[Path] = None) -> Optional[LLMConfig]:
    """Load and validate LLM config from YAML file.

    Returns None if the file doesn't exist (graceful degradation).
    Raises on validation errors.
    """
    config_path = path or _CONFIG_PATH
    if not config_path.exists():
        return None

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        return None

    return LLMConfig(**raw)


__all__ = [
    "LLMConfig",
    "ProviderConfig",
    "ProviderModels",
    "TaskOverride",
    "RateLimits",
    "CostAlert",
    "CacheConfig",
    "load_llm_config",
]
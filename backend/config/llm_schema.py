"""LLM 配置文件 schema 验证 (Pydantic).

Phase 16 — Hybrid AI 配置文件校验。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, model_validator


class ProviderModels(BaseModel):
    score: str = "qwen2.5:7b"
    tag: str = "qwen2.5:7b"
    ner: str = "qwen2.5:7b"
    summary: str = "qwen2.5:14b"
    chunk_summary: str = "qwen2.5:7b"
    # v0.7.4-image: IMAGE 档模型字段 (image_generation / image_understand 任务)
    # 留默认空串而非 None, 让既有 yaml 不补该字段也能落 schema
    image: str = ""


class ProviderConfig(BaseModel):
    type: Literal["ollama", "openai", "openai_compatible", "anthropic"]
    base_url: str | None = None
    api_key_env: str | None = None
    models: ProviderModels
    timeout_seconds: int = 30
    max_concurrent: int = 4
    # provider 特有的非标准请求体开关 (如关推理)。默认不改变请求体。
    extra_request_body: dict[str, Any] | None = None


class TaskOverride(BaseModel):
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 100
    batch_size: int | None = None
    # v0.7.4-image: image_generation override 专属字段 (公测期 watermark 默认 false)
    # 旧 override (t1_score/t3_summary/t3_chunk_summary) 不传 = 行为不变
    size: str | None = None
    n: int | None = None
    watermark: bool | None = None


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
    fallback_order: list[str] = ["ollama", "qwen", "openai"]
    providers: dict[str, ProviderConfig]
    task_overrides: dict[str, TaskOverride] | None = None
    rate_limits: RateLimits = RateLimits()
    cost_alert: CostAlert = CostAlert()
    cache: CacheConfig = CacheConfig()

    @model_validator(mode="after")
    def _validate_fallback_order(self) -> LLMConfig:
        for p in self.fallback_order:
            if p not in self.providers:
                raise ValueError(f"fallback_order provider '{p}' not in providers")
        return self

    @model_validator(mode="after")
    def _validate_default_provider(self) -> LLMConfig:
        if self.default_provider not in self.providers:
            raise ValueError(
                f"default_provider '{self.default_provider}' not in providers"
            )
        return self


_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "llm.yaml"


def load_llm_config(path: Path | None = None) -> LLMConfig | None:
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
    "CacheConfig",
    "CostAlert",
    "LLMConfig",
    "ProviderConfig",
    "ProviderModels",
    "RateLimits",
    "TaskOverride",
    "load_llm_config",
]
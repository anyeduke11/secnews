"""LLM 配置文件 schema 验证 (Pydantic).

Phase 16 — Hybrid AI 配置文件校验。
"""
from __future__ import annotations

import time
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


class ProviderBreaker(BaseModel):
    """v0.8.2 X-B1: per-provider 弹性阈值 (v0.8.1 PRD §7 推迟项偿还)。

    解析链: provider yaml 值 > env 全局 (HOTSPOT_BREAKER_*) > 内建默认 —
    特异性优先 (per-provider 调优理应压过全局 env); 未声明字段 = 沿用全局。
    字段语义与 ``provider_health.ProviderHealth`` 全局参数一一对应。
    """

    failure_threshold: float | None = None  # (0, 1] 5min 窗失败率阈值
    min_samples: int | None = None  # >= 1 判定最小样本数 (防单发误熔断)
    recovery_timeout: float | None = None  # > 0 breaker OPEN 时长秒

    @model_validator(mode="after")
    def _validate_ranges(self) -> ProviderBreaker:
        if self.failure_threshold is not None and not 0 < self.failure_threshold <= 1:
            raise ValueError("breaker.failure_threshold 必须在 (0, 1]")
        if self.min_samples is not None and self.min_samples < 1:
            raise ValueError("breaker.min_samples 必须 >= 1")
        if self.recovery_timeout is not None and self.recovery_timeout <= 0:
            raise ValueError("breaker.recovery_timeout 必须 > 0")
        return self


class ProviderConfig(BaseModel):
    # 2026-09-18 方案 B: +pi (pi.dev agent harness, 认证自管 ~/.pi/agent/auth.json,
    # 无 base_url / api_key_env 语义; 传输见 ai_hub/pi_transport.py)
    type: Literal["ollama", "openai", "openai_compatible", "anthropic", "pi"]
    base_url: str | None = None
    api_key_env: str | None = None
    models: ProviderModels
    timeout_seconds: int = 30
    max_concurrent: int = 4
    # provider 特有的非标准请求体开关 (如关推理)。默认不改变请求体。
    extra_request_body: dict[str, Any] | None = None
    # v0.8.2 X-B1: per-provider 断路器阈值 (不写 = 沿用 env 全局/内建默认)
    breaker: ProviderBreaker | None = None


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

# v0.8.2 Y-A2: llm.yaml 热重载 — 5s TTL + mtime/size 变更检测 (info_filter 模式)。
# 仅对默认路径 (path=None) 的调用生效; 显式 path (测试/特殊用途) 永不缓存。
# 返回的 LLMConfig 是**共享对象**, 调用方勿原地修改 (改了会污染缓存)。
_LLM_RELOAD_TTL = 5.0
_llm_cache: dict[str, Any] = {
    "mtime_ns": None,
    "size": None,
    "config": None,
    "checked_at": 0.0,
}


def load_llm_config(path: Path | None = None) -> LLMConfig | None:
    """Load and validate LLM config from YAML file.

    Returns None if the file doesn't exist (graceful degradation).
    Raises on validation errors.

    v0.8.2 Y-A2: 默认路径走 5s TTL 缓存 — TTL 窗口内直返上次解析结果,
    到期 stat 一次 mtime/size, 未变续期, 变了重解析 (热重载)。
    """
    config_path = path or _CONFIG_PATH

    global _llm_cache
    if path is None:
        now = time.monotonic()
        if (
            _llm_cache["config"] is not None
            and now - _llm_cache["checked_at"] < _LLM_RELOAD_TTL
        ):
            return _llm_cache["config"]

    if not config_path.exists():
        return None

    if path is None:
        st = config_path.stat()
        if (
            _llm_cache["config"] is not None
            and st.st_mtime_ns == _llm_cache["mtime_ns"]
            and st.st_size == _llm_cache["size"]
        ):
            _llm_cache["checked_at"] = time.monotonic()
            return _llm_cache["config"]

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        return None

    cfg = LLMConfig(**raw)
    if path is None:
        st = config_path.stat()
        _llm_cache.update(
            mtime_ns=st.st_mtime_ns, size=st.st_size, config=cfg,
            checked_at=time.monotonic(),
        )
    return cfg


def reset_llm_config_cache() -> None:
    """清空 llm.yaml 缓存 (测试/运维强制重读)。"""
    global _llm_cache
    _llm_cache = {"mtime_ns": None, "size": None, "config": None, "checked_at": 0.0}


__all__ = [
    "CacheConfig",
    "CostAlert",
    "LLMConfig",
    "ProviderBreaker",
    "ProviderConfig",
    "ProviderModels",
    "RateLimits",
    "TaskOverride",
    "load_llm_config",
    "reset_llm_config_cache",
]
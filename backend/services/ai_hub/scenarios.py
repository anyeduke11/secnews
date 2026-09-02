"""三场景模型路由 — deep/light/image (v0.7.4-image).

设计原则: 与 AIService._resolve_api_key / _key_source 同构 (Batch ⑥ 已落),
即四级链 ``env > settings.kv > router > default``。调用方拿到的是
``ScenarioRoute`` 数据类 (scenario/model/endpoint/max_tokens), 不直传 provider 字符串,
避免 ai_hub 内部出现 "model 在哪一层解析" 的认知分裂。

调用路径:
- AIService.evaluate(..., scenario=DEEP) → scenarios.resolve_scenario_model(DEEP)
- LLMService.generate(task="deep_read") → router HEAVY 档 → yaml t3_summary override (S1 落)
- ImageGenerationService.generate(...) → scenarios.resolve_scenario_model(IMAGE)

不在本批: yaml task_overrides 全展开 / 图片存储 / 多模态端到端 (留 v0.7.5+).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from backend.logging_config import logger

if TYPE_CHECKING:
    from backend.services.llm.model_router import ModelTier


class Scenario(str, Enum):
    DEEP = "deep"      # 长文深读 / 安全研判 / 多节结构化
    LIGHT = "light"    # 评分 / 分类 / 摘要 / 实体 / 限频热路径
    IMAGE = "image"    # 文生图 / 多模态图理解


@dataclass(frozen=True)
class ScenarioRoute:
    """场景 → 路由的不可变结果。"""
    scenario: Scenario
    model: str
    endpoint: str  # "/chat/completions" | "/v1/images/generations"
    max_tokens: int | None


# 单一兜底表 — 真值链全失败时回退到这里;env/kv/yaml 任意一层成功则覆盖
SCENARIO_DEFAULT_MODEL: dict[Scenario, str] = {
    Scenario.DEEP: "deepseek-v4-pro",          # yaml t3_summary override (S1 落) 会覆盖
    Scenario.LIGHT: "sensenova-6.8-flash-lite",
    Scenario.IMAGE: "sensenova-u1.5-lite",
}

SCENARIO_ENDPOINT: dict[Scenario, str] = {
    Scenario.DEEP: "/chat/completions",
    Scenario.LIGHT: "/chat/completions",
    Scenario.IMAGE: "/v1/images/generations",
}

SCENARIO_MAX_TOKENS: dict[Scenario, int | None] = {
    Scenario.DEEP: 1100,    # 对齐 deep_read_service.py:37 DEEP_READ_MAX_TOKENS
    Scenario.LIGHT: 600,    # 对齐 service.py:354 (evaluate/gate_detect)
    Scenario.IMAGE: None,   # image_generation 不传 max_tokens
}


def get_tier_for(scenario: Scenario) -> "ModelTier":
    """场景 → router tier (复用 model_router.ModelTier, 单一映射表)。"""
    from backend.services.llm.model_router import ModelTier
    return {
        Scenario.DEEP: ModelTier.HEAVY,
        Scenario.LIGHT: ModelTier.FLASH,
        Scenario.IMAGE: ModelTier.IMAGE,
    }[scenario]


def resolve_scenario_model(
    scenario: Scenario,
    *,
    provider: str | None = None,
    config: Any = None,
) -> ScenarioRoute:
    """四级链: env > settings.kv > router > default (与 AIService._resolve_api_key 同构).

    - env ``HOTSPOT_SCENARIO_{DEEP|LIGHT|IMAGE}_MODEL``: 运维首选, 进程内立即生效
    - settings.kv ``llm.scenario.{scenario}_model``: 用户切换 (S7 settings API 写入)
    - router ``route_model(scenario.value, config)``: yaml task_overrides 命中 (S1 落)
    - 兜底 ``SCENARIO_DEFAULT_MODEL[scenario]``

    失败不抛 — 与 _resolve_api_key 一致, fail-soft 返回 default。
    """
    env_key = f"HOTSPOT_SCENARIO_{scenario.value.upper()}_MODEL"
    if env_val := os.environ.get(env_key, "").strip():
        model = env_val
        logger.debug("scenarios[%s] resolved from env %s=%s", scenario.value, env_key, env_val)
    else:
        model = _settings_lookup(scenario) or _router_lookup(scenario, config)

    return ScenarioRoute(
        scenario=scenario,
        model=model or SCENARIO_DEFAULT_MODEL[scenario],
        endpoint=SCENARIO_ENDPOINT[scenario],
        max_tokens=SCENARIO_MAX_TOKENS[scenario],
    )


def _settings_lookup(scenario: Scenario) -> str:
    """settings.kv lookup — 走 SettingsRepository 单点 (Batch ⑥ 同款)。"""
    try:
        from backend.repository.settings_repo import SettingsRepository
        kv = SettingsRepository().get(f"llm.scenario.{scenario.value}_model")
        if isinstance(kv, str) and kv.strip():
            logger.debug("scenarios[%s] resolved from settings.kv: %s", scenario.value, kv)
            return kv.strip()
    except Exception as e:
        logger.debug("scenarios._settings_lookup(%s) swallow: %s", scenario.value, e)
    return ""


def _router_lookup(scenario: Scenario, config: Any) -> str:
    """router 路由 — 让 yaml task_overrides 显式 override 生效 (S1 配的 deepseek-v4-pro / u1.5-lite)。"""
    try:
        from backend.services.ai_hub import llm_service
        from backend.services.llm.model_router import route_model
        cfg = config or llm_service.config
        routed = route_model(scenario.value, config=cfg)
        if routed:
            return routed[1]
    except Exception as e:
        logger.debug("scenarios._router_lookup(%s) fallback: %s", scenario.value, e)
    return SCENARIO_DEFAULT_MODEL[scenario]


__all__ = [
    "Scenario",
    "ScenarioRoute",
    "SCENARIO_DEFAULT_MODEL",
    "SCENARIO_ENDPOINT",
    "SCENARIO_MAX_TOKENS",
    "get_tier_for",
    "resolve_scenario_model",
]

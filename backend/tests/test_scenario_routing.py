"""S2 验证 — scenarios.py 四级链解析 (v0.7.4-image).

四级链 (与 AIService._resolve_api_key 同构):
1. env HOTSPOT_SCENARIO_{DEEP|LIGHT|IMAGE}_MODEL
2. settings.kv 'llm.scenario.{scenario}_model'
3. router (yaml task_overrides 命中, S1 落)
4. SCENARIO_DEFAULT_MODEL 兜底
"""
from __future__ import annotations

import os
from unittest.mock import patch

from backend.services.ai_hub.scenarios import (
    SCENARIO_DEFAULT_MODEL,
    SCENARIO_ENDPOINT,
    SCENARIO_MAX_TOKENS,
    Scenario,
    ScenarioRoute,
    get_tier_for,
    resolve_scenario_model,
)


def test_env_overrides_settings_and_router(monkeypatch):
    """env 命中 → 最高优先级。"""
    monkeypatch.setenv("HOTSPOT_SCENARIO_DEEP_MODEL", "env-test-model")
    # 即使 mock 后续链全部返回别的, env 应胜
    with patch(
        "backend.services.ai_hub.scenarios._settings_lookup", return_value="kv-model"
    ), patch(
        "backend.services.ai_hub.scenarios._router_lookup", return_value="router-model"
    ):
        route = resolve_scenario_model(Scenario.DEEP)
    assert route.model == "env-test-model"


def test_settings_kv_overrides_router(monkeypatch):
    """env 未设 + kv 设了 → kv 胜, router 不被问。"""
    monkeypatch.delenv("HOTSPOT_SCENARIO_LIGHT_MODEL", raising=False)
    with patch(
        "backend.services.ai_hub.scenarios._settings_lookup", return_value="kv-light"
    ) as mock_kv, patch(
        "backend.services.ai_hub.scenarios._router_lookup"
    ) as mock_router:
        route = resolve_scenario_model(Scenario.LIGHT)
    assert route.model == "kv-light"
    assert mock_kv.called
    assert not mock_router.called, "kv 命中后 router 不应被问"


def test_router_lookup_when_no_env_no_kv(monkeypatch):
    """env 未设 + kv 空 → router 命中 (yaml task_overrides, S1 落 deepseek-v4-pro)."""
    monkeypatch.delenv("HOTSPOT_SCENARIO_DEEP_MODEL", raising=False)
    with patch(
        "backend.services.ai_hub.scenarios._settings_lookup", return_value=""
    ), patch(
        "backend.services.ai_hub.scenarios._router_lookup", return_value="deepseek-v4-pro"
    ):
        route = resolve_scenario_model(Scenario.DEEP)
    assert route.model == "deepseek-v4-pro"


def test_default_when_all_fail(monkeypatch):
    """全部失败 → SCENARIO_DEFAULT_MODEL 兜底。"""
    monkeypatch.delenv("HOTSPOT_SCENARIO_IMAGE_MODEL", raising=False)
    with patch(
        "backend.services.ai_hub.scenarios._settings_lookup", return_value=""
    ), patch(
        "backend.services.ai_hub.scenarios._router_lookup", return_value=""
    ):
        route = resolve_scenario_model(Scenario.IMAGE)
    assert route.model == SCENARIO_DEFAULT_MODEL[Scenario.IMAGE] == "sensenova-u1.5-lite"


def test_image_endpoint_is_images_generations():
    """IMAGE 场景 endpoint 是 /v1/images/generations (与 chat 分开)."""
    assert SCENARIO_ENDPOINT[Scenario.IMAGE] == "/v1/images/generations"
    assert SCENARIO_ENDPOINT[Scenario.DEEP] == "/chat/completions"
    assert SCENARIO_ENDPOINT[Scenario.LIGHT] == "/chat/completions"


def test_resolve_returns_complete_dataclass(monkeypatch):
    """resolve_scenario_model 返回完整字段 (scenario/model/endpoint/max_tokens)."""
    monkeypatch.delenv("HOTSPOT_SCENARIO_DEEP_MODEL", raising=False)
    with patch(
        "backend.services.ai_hub.scenarios._settings_lookup", return_value=""
    ), patch(
        "backend.services.ai_hub.scenarios._router_lookup", return_value="deepseek-v4-pro"
    ):
        route = resolve_scenario_model(Scenario.DEEP)
    assert isinstance(route, ScenarioRoute)
    assert route.scenario == Scenario.DEEP
    assert route.model == "deepseek-v4-pro"
    assert route.endpoint == "/chat/completions"
    assert route.max_tokens == 1100
    # IMAGE 端点不走 max_tokens
    with patch(
        "backend.services.ai_hub.scenarios._settings_lookup", return_value=""
    ), patch(
        "backend.services.ai_hub.scenarios._router_lookup", return_value="sensenova-u1.5-lite"
    ):
        route_img = resolve_scenario_model(Scenario.IMAGE)
    assert route_img.max_tokens is None
    assert route_img.max_tokens == SCENARIO_MAX_TOKENS[Scenario.IMAGE]


def test_get_tier_for_all_scenarios():
    """get_tier_for 是单一映射函数 — 改 tier 只动这一处。"""
    from backend.services.llm.model_router import ModelTier
    assert get_tier_for(Scenario.DEEP) == ModelTier.HEAVY
    assert get_tier_for(Scenario.LIGHT) == ModelTier.FLASH
    assert get_tier_for(Scenario.IMAGE) == ModelTier.IMAGE

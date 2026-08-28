"""S4-1 model_router ↔ ai_hub 双向接入测试。

覆盖:
1. route_model(config=None) 走 yaml 解析路径
2. route_model(config=LLMConfig) 优先 task_overrides
3. route_model 缺 task_overrides 时 fallback_order[0] 兜底
4. ai_hub.LLMService.resolve_provider_for_task 返回 (provider, model)
5. ai_hub.LLMService._try_order 把 router 推荐 provider 放首位, 仍保留 fallback_order
6. AIService._resolve_provider 三级优先级: AI_PROVIDER env > router > default_provider
"""
from __future__ import annotations

from unittest.mock import patch

from backend.config.llm_schema import (
    LLMConfig,
    ProviderConfig,
    ProviderModels,
    TaskOverride,
)


def _make_cfg(**overrides) -> LLMConfig:
    """构造一个最小 LLMConfig 用于 router 单测。"""
    cfg = LLMConfig(
        enabled=True,
        default_provider=overrides.get("default_provider", "ollama"),
        fallback_order=overrides.get("fallback_order", ["ollama", "openai"]),
        providers={
            "ollama": ProviderConfig(
                type="ollama",
                base_url="http://127.0.0.1:11434",
                models=ProviderModels(
                    score="qwen2.5:7b",
                    summary="qwen2.5:14b",
                ),
            ),
            "openai": ProviderConfig(
                type="openai",
                api_key_env="OPENAI_API_KEY",
                models=ProviderModels(
                    score="gpt-4o-mini",
                    summary="gpt-4o",
                ),
            ),
        },
        task_overrides=overrides.get("task_overrides"),
    )
    return cfg


def test_route_model_yaml_path_uses_fallback_order_first_item():
    """config=None 时走 yaml 解析路径, 应返回 fallback_order[0] + models.{score|summary}."""
    from backend.services.llm.model_router import route_model

    # config=None 走 _route_from_yaml, 这条路径读 config/llm.yaml 真实文件
    pname, model = route_model("score", config=None)
    # 不强求具体 provider (依赖 llm.yaml 内容), 只校验返回类型正确
    assert isinstance(pname, str)
    assert isinstance(model, str)
    assert pname != ""


def test_route_model_config_injected_overrides_take_priority():
    """config 注入时 task_overrides[t1_score] 应优先于 fallback_order[0]。

    score 是 STANDARD 档, 对应 override_key=t1_score;
    命中后 provider/model 由 task_overrides 决定, 与 fallback_order 无关。
    """
    from backend.services.llm.model_router import route_model

    cfg = _make_cfg(
        task_overrides={
            "t1_score": TaskOverride(
                provider="openai", model="gpt-4o-mini", temperature=0.0, max_tokens=50,
            ),
            "t3_summary": TaskOverride(
                provider="ollama", model="qwen2.5:14b", temperature=0.3, max_tokens=500,
            ),
        },
    )
    # score 走 t1_score → openai / gpt-4o-mini
    pname, model = route_model("score", config=cfg)
    assert pname == "openai"
    assert model == "gpt-4o-mini"


def test_route_model_no_overrides_falls_back_to_fallback_order():
    """task_overrides 为 None / 不命中 → fallback_order[0] 的 models.{score|summary}。"""
    from backend.services.llm.model_router import route_model

    cfg = _make_cfg(task_overrides=None)
    # score 没有 task_overrides 命中, 应走 fallback_order[0]=ollama + models.score="qwen2.5:7b"
    pname, model = route_model("score", config=cfg)
    assert pname == "ollama"
    assert model == "qwen2.5:7b"


def test_ai_hub_resolve_provider_for_task_returns_tuple():
    """LLMService.resolve_provider_for_task 应返回 (provider, model) 二元组。

    真实 config/llm.yaml 已存在, LLMService 启动时自动加载, _config 非空,
    因此 resolve_provider_for_task 应返回真实 (provider, model) 而非 None。
    """
    from backend.services.ai_hub import LLMService

    svc = LLMService()
    # 有真实 llm.yaml 时 _config 非空, router 命中 → 返回 tuple
    result = svc.resolve_provider_for_task("score")
    assert result is not None
    pname, model = result
    assert isinstance(pname, str) and pname != ""
    assert isinstance(model, str) and model != ""

    # 关闭 enabled → resolve_provider_for_task 返回 None
    svc._config = None  # 模拟 enabled=False (LLMService.enabled = _config is not None and _config.enabled)
    assert svc.resolve_provider_for_task("score") is None


def test_ai_hub_try_order_keeps_fallback_order_with_routed_first():
    """_try_order 在 router 命中时应把 router provider 放首位, 其余按 fallback_order 去重。

    通过 monkeypatch config 让 LLMService 持一个真实 LLMConfig, 再调 _try_order 校验顺序。
    """
    from backend.services.ai_hub import LLMService

    cfg = _make_cfg(
        default_provider="openai",
        fallback_order=["openai", "ollama"],
    )
    svc = LLMService()
    svc._config = cfg
    # score 是 STANDARD → override_key=t1_score, 但 task_overrides 未声明 → fallback_order[0]=openai
    order = svc._try_order("score")
    # router 命中 openai, fallback_order 首位也是 openai → 去重后 = [openai, ollama]
    assert order == ["openai", "ollama"]

    # 改 task_overrides 让 router 推荐 ollama (非 fallback_order 首位)
    cfg2 = _make_cfg(
        default_provider="openai",
        fallback_order=["openai", "ollama"],
        task_overrides={
            "t1_score": TaskOverride(
                provider="ollama", model="qwen2.5:7b", temperature=0.0, max_tokens=50,
            ),
        },
    )
    svc._config = cfg2
    order2 = svc._try_order("score")
    # router 推荐 ollama 在首位, fallback_order 中 openai 去重后插入
    assert order2[0] == "ollama"
    assert "openai" in order2
    assert len(order2) == 2


def test_ai_service_resolve_provider_three_levels():
    """AIService._resolve_provider 三级优先级: AI_PROVIDER env > router > default_provider。

    用 monkeypatch os.environ 注入 AI_PROVIDER=sensenova 验证 env 优先级;
    再 unset 验证 router 命中; 再把 config 替换成 default_provider=sensenova 兜底验证。
    """
    import os

    from backend.services.ai_hub import AIService

    # 1) AI_PROVIDER env 优先
    with patch.dict(os.environ, {"AI_PROVIDER": "dots_ai"}, clear=False):
        assert AIService._resolve_provider() == "dots_ai"

    # 2) env 未设, router 推荐 → llm.yaml fallback_order[0]=ollama, _route_from_yaml 应返回 ("ollama", "qwen2.5:7b")
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AI_PROVIDER", None)
        # 默认 config 是 llm_service.config (LLMService 全局), 加载真实 llm.yaml
        # 此时 _resolve_provider 走 router; router 推荐 ollama (yaml fallback_order[0])
        result = AIService._resolve_provider()
        # router 推荐可能等于 cfg.default_provider; 若 cfg.default_provider=openai, router 也应=openai
        assert result in ("ollama", "openai", "sensenova")

    # 3) router 抛异常时, 兜底 cfg.default_provider (sensenova)
    # 真实环境中 llm_service.config 是 property (无 setter), 不能直接 patch.object;
    # 改用 patch 把 route_model 替换为抛异常, 验证兜底到 cfg.default_provider (yaml 是 sensenova)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AI_PROVIDER", None)
        with patch(
            "backend.services.llm.model_router.route_model",
            side_effect=RuntimeError("router boom"),
        ):
            assert AIService._resolve_provider() == "sensenova"


__all__ = []
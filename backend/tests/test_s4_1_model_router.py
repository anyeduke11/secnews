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
    # P0-1: t1_score.model 允许空串 (pi 语义 = 不下传 --model);
    # "非空 model" 的回归锚由 TestResolveModelConsumesOverride
    # .test_real_yaml_deep_read_uses_declared_model 承担 (deep_read 档)
    assert isinstance(model, str)

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

    # 2) env 未设, router 命中 → 与 route_model("evaluate") 的推荐一致
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AI_PROVIDER", None)
        # _resolve_provider 内部即调 route_model("evaluate", config=llm_service.config);
        # STANDARD 档命中 t1_score override, 其 provider 随 llm.yaml 演进 (当前 pi),
        # 故断言对齐 router 实际推荐而非写死 provider 名
        from backend.services.ai_hub.gateway import llm_service
        from backend.services.llm.model_router import route_model

        expected = route_model("evaluate", config=llm_service.config)[0]
        assert AIService._resolve_provider() == expected

    # 3) router 抛异常时, 兜底 cfg.default_provider
    # 真实环境中 llm_service.config 是 property (无 setter), 不能直接 patch.object;
    # 改用 patch 把 route_model 替换为抛异常, 验证兜底到 cfg.default_provider。
    # 2026-09-27 pi 主力化后 yaml default=pi, 断言锚定配置现值 (default 翻转时意图不变)。
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AI_PROVIDER", None)
        from backend.services.ai_hub.gateway import llm_service as _svc

        cfg_default = _svc.config.default_provider
        with patch(
            "backend.services.llm.model_router.route_model",
            side_effect=RuntimeError("router boom"),
        ):
            assert AIService._resolve_provider() == cfg_default


__all__ = []


# ============================================================================
# P0-1 (v0.8.6 / 审计 E1): _resolve_model 真实消费 task_overrides.model
# ============================================================================
# WHY: 此前 _try_order 只取 routed[0] (provider 半边), model 半边被丢弃 —
# override.model 是纯装饰: deep_read 恒跑 models.summary (flash-lite) 而
# 非 override 声明的 deepseek-v4-pro; DEV-0245 的"一键写入路由"写入的
# model 字段因此不生效。以下用例锁定修复语义。


class TestResolveModelConsumesOverride:
    def test_override_model_used_when_provider_matches(self):
        """override 命中位: _resolve_model 必须返回 override.model 而非 models.summary。

        deep_read → HEAVY 档 → t3_summary override (openai/gpt-4o);
        修复前返回 openai 的 models.summary=gpt-4o (恰好同值, 换模型即暴露),
        此处用 openai models.summary=gpt-4o + override model=custom-x 分离两者。
        """
        from backend.services.ai_hub import LLMService

        cfg = _make_cfg(
            task_overrides={
                "t3_summary": TaskOverride(
                    provider="openai", model="custom-heavy-x",
                    temperature=0.3, max_tokens=500,
                ),
            },
        )
        svc = LLMService()
        svc._config = cfg
        assert svc._resolve_model("openai", "deep_read") == "custom-heavy-x"

    def test_fallback_position_keeps_models_mapping(self):
        """非 override 命中位 (fallback 尝试): 沿用 models.* 映射, 行为不变。"""
        from backend.services.ai_hub import LLMService

        cfg = _make_cfg(
            fallback_order=["ollama", "openai"],
            task_overrides={
                "t3_summary": TaskOverride(
                    provider="openai", model="custom-heavy-x",
                    temperature=0.3, max_tokens=500,
                ),
            },
        )
        svc = LLMService()
        svc._config = cfg
        # ollama 是 fallback 位 → 用自己的 models.summary
        assert svc._resolve_model("ollama", "deep_read") == "qwen2.5:14b"

    def test_empty_override_model_falls_back_to_mapping(self):
        """override.model 为空串 (pi 语义: 不下传 --model) → 沿用映射 (pi 即空)。"""
        from backend.services.ai_hub import LLMService
        from backend.config.llm_schema import LLMConfig, ProviderConfig, ProviderModels

        cfg = LLMConfig(
            enabled=True,
            default_provider="pi",
            fallback_order=["pi", "ollama"],
            providers={
                # pi 与真实 llm.yaml 一致: 五槽显式空串 (schema 无参默认非空,
                # 会掩盖 "空串 = 不下传 --model" 语义)
                "pi": ProviderConfig(
                    type="pi",
                    models=ProviderModels(
                        score="", tag="", ner="", summary="", chunk_summary="",
                    ),
                ),
                "ollama": ProviderConfig(
                    type="ollama", base_url="http://127.0.0.1:11434",
                    models=ProviderModels(score="qwen2.5:7b", summary="qwen2.5:14b"),
                ),
            },
            task_overrides={
                "t1_score": TaskOverride(
                    provider="pi", model="", temperature=0.0, max_tokens=512,
                ),
            },
        )
        svc = LLMService()
        svc._config = cfg
        # 空 model → 不采用 override → pi 的 models.score 为空 → "" (不下传 --model)
        assert svc._resolve_model("pi", "score") == ""

    def test_real_yaml_deep_read_uses_declared_model(self):
        """真实 llm.yaml 回归锚: deep_read 在 t3_summary 声明位必须解析出声明模型。

        锁定审计 E1 的验收语义: deep_read 实际模型 = override 声明值
        (sensenova/deepseek-v4-pro), 不再恒跑 flash-lite。yaml 改档时此
        断言跟随 fail, 强制同步认知。
        """
        from backend.services.ai_hub import LLMService

        svc = LLMService()  # 加载真实 config/llm.yaml
        routed = svc.resolve_provider_for_task("deep_read")
        assert routed is not None
        pname, model = routed
        assert model, "t3_summary override 声明了 model, router 不应返回空"
        assert svc._resolve_model(pname, "deep_read") == model
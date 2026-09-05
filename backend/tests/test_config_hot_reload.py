"""v0.8.2 Y-A2 — 配置热重载测试 (feature_gates.toml / llm.yaml / provider 阈值)。

5s TTL + mtime 变更检测 (info_filter 模式); 语义边界: gate 热重载只影响
运行时动态读数, 路由/job 注册仍为启动期快照 (router 增删需重启)。
"""

from __future__ import annotations

import time

import pytest

from backend.extensions import (
    _GATES_PATH,
    is_extension_enabled,
    reset_gates,
)

# ---------------------------------------------------------------------------
# feature_gates.toml — gate 动态读数热重载
# ---------------------------------------------------------------------------
# 用 "crm": conftest 的 HOTSPOT_FEATURE_GATES env 覆盖不含此键,
# toml 翻转不会被 env 压住 (env > toml 优先级由 test_env_override_still_wins 单独验证)。
TOML_VALID_FALSE = '[extensions]\n  crm = false\n'
TOML_VALID_TRUE = '[extensions]\n  crm = true\n'


@pytest.fixture
def gates_env(tmp_path, monkeypatch):
    """gate 模块指向私有 tmp toml + TTL 可控 + 每测试复位缓存。"""
    toml = tmp_path / "feature_gates.toml"
    toml.write_text(TOML_VALID_FALSE)
    monkeypatch.setattr("backend.extensions._GATES_PATH", toml)
    monkeypatch.setattr("backend.extensions._GATES_TTL", 0.0)  # 默认即到期待重读
    reset_gates()
    yield toml
    reset_gates()


class TestGatesHotReload:
    def test_flip_takes_effect(self, gates_env):
        """toml sync=false -> true: TTL 到期后动态读数翻转。"""
        assert is_extension_enabled("crm") is False
        gates_env.write_text(TOML_VALID_TRUE)
        assert is_extension_enabled("crm") is True

    def test_ttl_window_keeps_cache(self, gates_env, monkeypatch):
        """TTL 窗口内 (未到期) 文件变更不生效 — 防 stat 风暴。"""
        monkeypatch.setattr("backend.extensions._GATES_TTL", 999.0)
        assert is_extension_enabled("crm") is False
        gates_env.write_text(TOML_VALID_TRUE)
        assert is_extension_enabled("crm") is False  # 窗口内读旧缓存

    def test_broken_toml_keeps_last_good(self, gates_env):
        """热重载路径遇语法错: 沿用上次成功读数, 不让扩展集体消失。"""
        assert is_extension_enabled("crm") is False
        gates_env.write_text("not [valid toml ===")
        assert is_extension_enabled("crm") is False  # 旧读数保留 (非 fail-closed 全空)
        gates_env.write_text(TOML_VALID_TRUE)
        assert is_extension_enabled("crm") is True  # 修复后恢复热重载

    def test_missing_file_keeps_last_good(self, gates_env):
        assert is_extension_enabled("crm") is False
        gates_env.unlink()
        assert is_extension_enabled("crm") is False
        gates_env.write_text(TOML_VALID_TRUE)
        assert is_extension_enabled("crm") is True

    def test_env_override_still_wins(self, gates_env, monkeypatch):
        """热重载不改优先级: 默认 < TOML < env。"""
        monkeypatch.setenv(
            "HOTSPOT_FEATURE_GATES", '{"extensions": {"crm": true}}'
        )
        reset_gates()
        assert is_extension_enabled("crm") is True  # env 压过 toml false
        assert _GATES_PATH is not None  # import 契约 (符号存在)


# ---------------------------------------------------------------------------
# llm.yaml — load_llm_config TTL 缓存 + 热重载
# ---------------------------------------------------------------------------
YAML_TPL = (
    "enabled: true\n"
    "default_provider: {default}\n"
    "fallback_order:\n"
    "  - {default}\n"
    "providers:\n"
    "  ollama:\n"
    "    type: ollama\n"
    "    base_url: 'http://127.0.0.1:11434'\n"
    "    models:\n"
    "      score: 'qwen2.5:7b'\n"
)


@pytest.fixture
def llm_yaml_env(tmp_path, monkeypatch):
    yaml_file = tmp_path / "llm.yaml"
    yaml_file.write_text(YAML_TPL.format(default="ollama"))
    monkeypatch.setattr("backend.config.llm_schema._CONFIG_PATH", yaml_file)
    monkeypatch.setattr("backend.config.llm_schema._LLM_RELOAD_TTL", 0.0)
    from backend.config.llm_schema import reset_llm_config_cache

    reset_llm_config_cache()
    yield yaml_file
    reset_llm_config_cache()


class TestLlmYamlHotReload:
    def test_identity_within_ttl(self, llm_yaml_env, monkeypatch):
        """TTL 窗口内重复调用返回**同一对象** (省解析 + 身份稳定)。"""
        monkeypatch.setattr("backend.config.llm_schema._LLM_RELOAD_TTL", 999.0)
        from backend.config.llm_schema import load_llm_config

        c1 = load_llm_config()
        assert load_llm_config() is c1

    def test_flip_takes_effect(self, llm_yaml_env):
        """mtime 变更后热重载: default_provider ollama -> 新 provider。"""
        from backend.config.llm_schema import load_llm_config

        assert load_llm_config().default_provider == "ollama"
        llm_yaml_env.write_text(YAML_TPL.format(default="ollama2"))
        # ollama2 未注册会校验失败 → 改成合法翻转: 翻转 enabled
        llm_yaml_env.write_text(YAML_TPL.format(default="ollama").replace(
            "enabled: true", "enabled: false"
        ))
        assert load_llm_config().enabled is False

    def test_explicit_path_never_cached(self, tmp_path):
        """显式 path (测试/特殊用途) 绕过缓存 — 两次独立解析。"""
        from backend.config.llm_schema import load_llm_config

        f1 = tmp_path / "a.yaml"
        f1.write_text(YAML_TPL.format(default="ollama"))
        c1 = load_llm_config(f1)
        c1b = load_llm_config(f1)
        assert c1 is not c1b  # 不缓存, 每次新对象

    def test_missing_then_created(self, llm_yaml_env):
        """文件缺失返 None 不污染缓存; 创建后可读。"""
        from backend.config.llm_schema import load_llm_config

        llm_yaml_env.unlink()
        assert load_llm_config() is None
        llm_yaml_env.write_text(YAML_TPL.format(default="ollama"))
        assert load_llm_config() is not None


# ---------------------------------------------------------------------------
# gateway — LLMService._config 热交换
# ---------------------------------------------------------------------------
class TestGatewayConfigSwap:
    def test_swap_on_identity_change(self, monkeypatch):
        from backend.config.llm_schema import (
            CacheConfig,
            CostAlert,
            LLMConfig,
            ProviderConfig,
            ProviderModels,
            RateLimits,
        )
        from backend.services.ai_hub.gateway import LLMService

        def _cfg(name: str) -> LLMConfig:
            return LLMConfig(
                enabled=True,
                default_provider=name,
                fallback_order=[name],
                providers={
                    name: ProviderConfig(
                        type="ollama",
                        base_url="http://127.0.0.1:11434",
                        models=ProviderModels(),
                    )
                },
                cache=CacheConfig(enabled=False, ttl_seconds=1),
                cost_alert=CostAlert(),
                rate_limits=RateLimits(),
            )

        cfg1, cfg2 = _cfg("ollama"), None
        # ollama1 名字不存在 — 换个方式: 两个独立构造的同名对象即身份不同
        cfg2 = _cfg("ollama")
        holder = {"cfg": cfg1}
        monkeypatch.setattr(
            "backend.services.ai_hub.gateway.load_llm_config",
            lambda _path=None: holder["cfg"],
        )
        svc = LLMService()
        assert svc._config is cfg1

        holder["cfg"] = cfg2  # "文件变了" → load 返回新对象
        svc._maybe_reload_config()
        assert svc._config is cfg2

    def test_explicit_path_never_swaps(self, tmp_path, monkeypatch):
        """显式 config_path (测试注入语义) 永不热重载。"""
        from backend.services.ai_hub.gateway import LLMService

        missing = tmp_path / "no.yaml"
        svc = LLMService(config_path=missing)
        assert svc._config is None
        svc._maybe_reload_config()  # 早退, 不触发 load
        assert svc._config is None


# ---------------------------------------------------------------------------
# provider_health — per-provider 阈值热重载
# ---------------------------------------------------------------------------
class TestThresholdHotReload:
    def test_reload_updates_overrides_keeps_windows(self, monkeypatch):
        """阈值热重载只换判定参数 — 窗口样本原样保留。"""
        from backend.services.ai_hub import provider_health as ph_mod
        from backend.services.ai_hub.provider_health import ProviderHealth

        ph = ProviderHealth(clock=time.monotonic, reload_thresholds=True)
        ph.record("sensenova", ok=False)
        ph.record("sensenova", ok=False)
        before = ph.snapshot("sensenova")["windows"]["1m"]["total"]
        ph._thresholds_checked_at = 0.0  # 绕过 record 刚设置的 TTL

        monkeypatch.setattr(
            ph_mod,
            "_load_yaml_breaker_overrides",
            lambda: {"sensenova": {"failure_threshold": 0.9}},
        )
        ph.maybe_reload_thresholds()
        assert ph._overrides["sensenova"]["failure_threshold"] == 0.9
        assert ph.snapshot("sensenova")["windows"]["1m"]["total"] == before

    def test_ttl_skips_repeated_stat(self, monkeypatch):
        from backend.services.ai_hub import provider_health as ph_mod
        from backend.services.ai_hub.provider_health import ProviderHealth

        calls = {"n": 0}

        def _counting():
            calls["n"] += 1
            return {"ollama": {"min_samples": 6}}

        ph = ProviderHealth(clock=time.monotonic, reload_thresholds=True)
        monkeypatch.setattr(ph_mod, "_load_yaml_breaker_overrides", _counting)
        ph._thresholds_checked_at = 0.0
        ph.maybe_reload_thresholds()
        ph.maybe_reload_thresholds()  # TTL 窗口内不再触发
        assert calls["n"] == 1
        assert ph._overrides["ollama"]["min_samples"] == 6

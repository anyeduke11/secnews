"""AIService._resolve_provider / _config_source settings.kv 覆盖层测试 (v0.7 Batch 2)。

覆盖:
- env > settings.kv > router > default 四级优先级
- settings.kv 异常 / 类型异常 全吞, 不影响主链
- 端到端: 切换 settings.kv 后 ``_record`` 写入的 ``config_source`` 反映新路径
- ``_config_source`` 与 ``_resolve_provider`` 走同一链, 一致性
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch


def _ensure_settings_table(db_path):
    """测试隔离: 确保 settings 表存在 (走 settings_repo 实际路径)。"""
    from backend.repository.settings_repo import SettingsRepository
    SettingsRepository.set = SettingsRepository.set.__get__(SettingsRepository())
    SettingsRepository().set("__probe__.init", None)


def test_env_wins_over_settings_kv(monkeypatch):
    """env 设 + settings.kv 设 → env 赢 (env 是运维最高优先级)。

    与 Batch 1 ``test_s4_1_model_router::test_ai_service_resolve_provider_three_levels``
    共存: env 优先级不变, settings.kv 只是新增的一层。
    """
    import os

    from backend.repository.settings_repo import SettingsRepository
    from backend.services.ai_hub import AIService

    SettingsRepository().set("llm.default_provider", "ollama")

    with patch.dict(os.environ, {"AI_PROVIDER": "dots_ai"}, clear=False):
        result = AIService._resolve_provider()
        assert result == "dots_ai"
        assert AIService._config_source() == "env"

    SettingsRepository().delete("llm.default_provider")


def test_settings_kv_wins_when_env_unset(monkeypatch):
    """env 未设 + settings.kv 设 → settings.kv 赢 (Batch 2 核心承诺)。"""
    import os

    from backend.repository.settings_repo import SettingsRepository
    from backend.services.ai_hub import AIService

    os.environ.pop("AI_PROVIDER", None)
    SettingsRepository().set("llm.default_provider", "qwen")

    assert AIService._resolve_provider() == "qwen"
    assert AIService._config_source() == "settings"

    SettingsRepository().delete("llm.default_provider")


def test_router_wins_when_env_and_settings_unset():
    """env 未设 + settings.kv 未设 + router 推荐 → router 赢 (既有三级链)。"""
    import os

    from backend.repository.settings_repo import SettingsRepository
    from backend.services.ai_hub import AIService

    os.environ.pop("AI_PROVIDER", None)
    SettingsRepository().delete("llm.default_provider")

    result = AIService._resolve_provider()
    # llm.yaml 默认 sensenova + fallback_order [ollama, sensenova, qwen, openai];
    # router 推荐顺序不固定, 但应在 yaml 注册的 5 个 provider 之内
    assert result in ("sensenova", "ollama", "openai", "qwen", "anthropic")
    assert AIService._config_source() in ("router", "default")


def test_default_fallback_when_router_raises():
    """env/settings.kv/router 全失败 → 兜底 cfg.default_provider (sensenova)。"""
    import os

    from backend.repository.settings_repo import SettingsRepository
    from backend.services.ai_hub import AIService

    os.environ.pop("AI_PROVIDER", None)
    SettingsRepository().delete("llm.default_provider")

    with patch(
        "backend.services.llm.model_router.route_model",
        side_effect=RuntimeError("router boom"),
    ):
        assert AIService._resolve_provider() == "sensenova"
        assert AIService._config_source() == "default"


def test_settings_kv_non_string_value_is_skipped():
    """settings.kv 设为非字符串 (int / list / dict) → 跳过, 退回 router/default。"""
    import os

    from backend.repository.settings_repo import SettingsRepository
    from backend.services.ai_hub import AIService

    os.environ.pop("AI_PROVIDER", None)
    # 非字符串值: 模拟 typo 把 list / dict 误写进 KV
    SettingsRepository().set("llm.default_provider", ["ollama", "sensenova"])

    result = AIService._resolve_provider()
    assert result in ("sensenova", "ollama", "openai", "qwen", "anthropic")
    # 跳过非字符串后, 应该走 router/default 路径
    assert AIService._config_source() in ("router", "default")

    SettingsRepository().delete("llm.default_provider")


def test_settings_kv_empty_string_is_skipped():
    """settings.kv 设为空字符串 / 全空格 → 跳过 (避免空串被当成合法 provider 名)。"""
    import os

    from backend.repository.settings_repo import SettingsRepository
    from backend.services.ai_hub import AIService

    os.environ.pop("AI_PROVIDER", None)
    SettingsRepository().set("llm.default_provider", "   ")

    result = AIService._resolve_provider()
    assert result != "" and result.strip() != ""

    SettingsRepository().delete("llm.default_provider")


def test_settings_repo_failure_does_not_break_chain():
    """settings_repo.get 抛 sqlite 错 → 吞, 不影响主链, 退回 router/default。"""
    import os

    from backend.repository.settings_repo import SettingsRepository
    from backend.services.ai_hub import AIService

    os.environ.pop("AI_PROVIDER", None)

    def _boom(_key, default=None):
        raise sqlite3.OperationalError("settings table missing")

    with patch.object(SettingsRepository, "get", side_effect=_boom):
        # 不应抛 — settings.kv 路径吞掉, 退到 router
        result = AIService._resolve_provider()
        assert isinstance(result, str) and result


def test_record_carries_config_source_end_to_end(monkeypatch):
    """_record 写入 llm_usage_log 时 config_source 字段反映 settings.kv 路径。

    端到端契约: 当前端切换到 ollama 时, 调用 evaluate() 落库的 config_source
    应是 'settings' 而非 'default' / 'router'。
    """
    import os

    from backend.repository.db import get_connection
    from backend.repository.settings_repo import SettingsRepository
    from backend.services.ai_hub import AIService

    os.environ.pop("AI_PROVIDER", None)
    SettingsRepository().set("llm.default_provider", "ollama")

    # mock _call_ollama_eval 返回成功, 锁定 _record 路径
    fake_result = {
        "ok": True,
        "provider": "ollama",
        "quality_score": 8.0,
        "verdict": "好",
        "summary": "fake",
        "key_points": ["a", "b"],
    }
    with patch.object(AIService, "_call_ollama_eval", return_value=fake_result), \
         patch.object(AIService, "_cache_get", return_value=None), \
         patch.object(AIService, "_cache_set", return_value=None):
        result = AIService().evaluate("dummy", title="t", provider="ollama")
        assert result["ok"] is True

    # 查 llm_usage_log 看 config_source
    row = get_connection().execute(
        "SELECT config_source, provider FROM llm_usage_log ORDER BY occurred_at DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row["provider"] == "ollama"
    # 因为 _call_ollama_eval 直接返回, 跳过了 _resolve_provider,
    # 但 _config_source() 仍被 _record 调用, 此时 env=None + settings.kv=ollama → 'settings'
    assert row["config_source"] == "settings"

    SettingsRepository().delete("llm.default_provider")

"""ai_hub 模型池单测 (DEV-0244) — 无真实出站。

覆盖:
- PRESETS 完整性 (name 唯一 / base_url https / 与 egress 白名单一致)
- resolve_preset_key: env 主名 > 别名 > secrets > none
- probe_platform: mock httpx.get — 200 建模型列表 / 401 密钥无效 / 404 unknown
- pool_snapshot: probe=False 零出站且 pi 永不在 platforms (owner 裁决: pi 是 Agent)
"""

from __future__ import annotations

from pathlib import Path

from backend.services.ai_hub import pool as pool_mod
from backend.services.ai_hub.egress import TRUSTED_LLM_HOSTS
from backend.services.ai_hub.pool import (
    AGENT_CHANNELS,
    PLATFORM_PRESETS,
    pool_snapshot,
    probe_platform,
    resolve_preset_key,
)


class TestPresets:
    def test_names_unique_and_https(self):
        names = [p.name for p in PLATFORM_PRESETS]
        assert len(names) == len(set(names))
        for p in PLATFORM_PRESETS:
            assert p.base_url.startswith("https://"), f"{p.name} 必须 https"
            assert p.key_env.isupper()

    def test_all_hosts_in_egress_whitelist(self):
        """附带凭据出站必须过 egress 门 — 目录与白名单漂移即 CI 红。"""
        from urllib.parse import urlsplit
        for p in PLATFORM_PRESETS:
            host = (urlsplit(p.base_url).hostname or "").lower()
            assert host in TRUSTED_LLM_HOSTS, f"{p.name} 的 {host} 未登记 egress.py"

    def test_pi_is_agent_channel_not_platform(self):
        """owner 裁决: pi 是 Agent 不是模型 — 不得混入平台目录。"""
        names = {p.name for p in PLATFORM_PRESETS}
        assert "pi" not in names
        assert any(a["name"] == "pi" for a in AGENT_CHANNELS)


class TestResolveKey:
    def test_env_primary_then_alias(self, monkeypatch):
        monkeypatch.delenv("QWEN_API_KEY", raising=False)
        monkeypatch.setenv("DASHSCOPE_API_KEY", "alias-key")
        key, src = resolve_preset_key("qwen")
        assert (key, src) == ("alias-key", "env")
        monkeypatch.setenv("QWEN_API_KEY", "primary-key")
        key, src = resolve_preset_key("qwen")
        assert (key, src) == ("primary-key", "env")

    def test_unknown_platform_none(self, monkeypatch):
        monkeypatch.delenv("SENSENOVA_API_KEY", raising=False)
        key, src = resolve_preset_key("nope")
        assert (key, src) == ("", "none")

    def test_secrets_fallback(self, monkeypatch, tmp_path: Path):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

        class _Item:
            id = 7
            encryption_key_id = "k1"

        class _Repo:
            def get_by_provider(self, provider):
                assert provider == "deepseek"
                return _Item()

        class _Svc:
            def decrypt_for_internal_use(self, item_id):
                return "vault-key"

        import backend.repository.secrets_repo as sr
        import backend.services.secrets_service as ss
        monkeypatch.setattr(sr, "SecretRepository", _Repo)
        monkeypatch.setattr(ss, "SecretsService", _Svc)
        monkeypatch.setattr(ss, "_is_unlocked", lambda kid: True)
        key, src = resolve_preset_key("deepseek")
        assert (key, src) == ("vault-key", "secrets")


class TestProbe:
    def _preset(self):
        return PLATFORM_PRESETS[1]  # deepseek

    def test_models_listed(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "k")

        class _Resp:
            status_code = 200
            def json(self):
                return {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}

        import backend.services.ai_hub.pool as pm
        monkeypatch.setattr(pm.httpx, "get", lambda *a, **kw: _Resp())
        out = probe_platform(self._preset())
        assert out["available"] is True
        assert out["models"] == ["deepseek-chat", "deepseek-reasoner"]
        assert out["model_count"] == 2

    def test_invalid_key_401(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "bad")

        class _Resp:
            status_code = 401
            def json(self):
                return {}

        import backend.services.ai_hub.pool as pm
        monkeypatch.setattr(pm.httpx, "get", lambda *a, **kw: _Resp())
        out = probe_platform(self._preset())
        assert out["available"] is False
        assert "401" in (out["error"] or "")

    def test_no_models_endpoint_unknown(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "k")

        class _Resp:
            status_code = 404
            def json(self):
                return {}

        import backend.services.ai_hub.pool as pm
        monkeypatch.setattr(pm.httpx, "get", lambda *a, **kw: _Resp())
        out = probe_platform(self._preset())
        assert out["available"] is None
        assert out["error"] == "platform_no_models_endpoint"

    def test_no_key_short_circuit(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setattr(pool_mod, "resolve_preset_key", lambda n: ("", "none"))
        called = {"n": 0}

        import backend.services.ai_hub.pool as pm
        def _boom(*a, **kw):
            called["n"] += 1
            raise AssertionError("no_key 时不得出站")
        monkeypatch.setattr(pm.httpx, "get", _boom)
        out = probe_platform(self._preset())
        assert out["available"] is False and out["error"] == "no_key"
        assert called["n"] == 0


class TestSnapshot:
    def test_unprobed_zero_egress_pi_separated(self, monkeypatch):
        monkeypatch.delenv("SENSENOVA_API_KEY", raising=False)
        monkeypatch.setattr(pool_mod, "resolve_preset_key", lambda n: ("", "none"))
        snap = pool_snapshot(probe=False)
        assert snap["probed"] is False
        assert len(snap["platforms"]) == len(PLATFORM_PRESETS)
        assert all(p["name"] != "pi" for p in snap["platforms"])
        assert any(a["name"] == "pi" for a in snap["agent_channels"])

    def test_probe_only_filters(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "k")

        class _Resp:
            status_code = 200
            def json(self):
                return {"data": [{"id": "deepseek-chat"}]}

        import backend.services.ai_hub.pool as pm
        monkeypatch.setattr(pm.httpx, "get", lambda *a, **kw: _Resp())
        snap = pool_snapshot(probe=True, only="deepseek")
        assert [p["name"] for p in snap["platforms"]] == ["deepseek"]
        assert snap["platforms"][0]["model_count"] == 1

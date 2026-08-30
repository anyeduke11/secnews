"""C3 出站凭据门禁单测: 白名单、scheme 拒绝、环境变量追加。"""
from __future__ import annotations

import pytest

from backend.services.ai_hub.egress import (
    TRUSTED_LLM_HOSTS,
    EgressNotAllowedError,
    allowed_hosts,
    check_credential_egress,
    host_of,
)


def test_real_provider_hosts_pass():
    """config/llm.yaml 里 5 个带凭据的 provider 必须原样通过, 否则改完就断服。"""
    for url in (
        "https://token.sensenova.cn/v1",
        "https://api.sensenova.cn/v1",
        "https://api.dots.ai/v1",
        "https://api.openai.com/v1",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "https://api.anthropic.com/v1",
    ):
        assert check_credential_egress(url) == host_of(url)


def test_plaintext_http_refused_even_for_trusted_host():
    with pytest.raises(EgressNotAllowedError):
        check_credential_egress("http://api.openai.com/v1")


def test_attacker_host_refused(monkeypatch):
    monkeypatch.delenv("HOTSPOT_LLM_ALLOWED_HOSTS", raising=False)
    with pytest.raises(EgressNotAllowedError) as ei:
        check_credential_egress("https://evil.example.net/v1")
    assert "evil.example.net" in str(ei.value)


@pytest.mark.parametrize("url", [
    "https://169.254.169.254/latest/meta-data",   # 云元数据
    "https://127.0.0.1:9999/v1",                   # 指向回环的伪 provider
    "https://attacker.com",                        # 无路径
    "",                                            # 空
    "not-a-url",                                   # 不可解析
    "https://user:pw@token.sensenova.cn/v1",       # userinfo 混淆
])
def test_hostile_or_malformed_urls_refused(url, monkeypatch):
    """userinfo 混淆必须失败: 凭据不能因 URL 前缀伪装而被放行。"""
    monkeypatch.delenv("HOTSPOT_LLM_ALLOWED_HOSTS", raising=False)
    with pytest.raises(EgressNotAllowedError):
        check_credential_egress(url)


def test_env_var_extends_allowlist(monkeypatch):
    monkeypatch.setenv("HOTSPOT_LLM_ALLOWED_HOSTS", "llm.internal.example , api.newprov.io")
    assert "api.newprov.io" in allowed_hosts()
    assert "llm.internal.example" in allowed_hosts()
    assert check_credential_egress("https://api.newprov.io/v1") == "api.newprov.io"


def test_env_var_cannot_silently_narrow_builtin_allowlist(monkeypatch):
    """追加语义: 设了环境变量也不该让内置主机失效。"""
    monkeypatch.setenv("HOTSPOT_LLM_ALLOWED_HOSTS", "only.this.example")
    assert allowed_hosts() >= TRUSTED_LLM_HOSTS
    assert check_credential_egress("https://api.openai.com/v1") == "api.openai.com"


def test_case_insensitive_host_match(monkeypatch):
    monkeypatch.delenv("HOTSPOT_LLM_ALLOWED_HOSTS", raising=False)
    assert check_credential_egress("https://API.OpenAI.COM/v1") == "api.openai.com"


class _RecordingClient:
    """替身 httpx.AsyncClient: 记录每个真实发出的请求。"""

    calls: list[tuple[str, dict]] = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        _RecordingClient.calls.append((url, dict(headers or {})))

        class _R:
            def raise_for_status(self):
                pass

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": "ok"}}]}

        return _R()


def test_wired_into_call_openai_no_key_leaks(monkeypatch):
    """守卫确实接在 _call_openai 上: 恶意 base_url 一个请求都发不出去。"""
    import asyncio

    from backend.config.llm_schema import ProviderConfig
    from backend.services.ai_hub import gateway as G

    monkeypatch.delenv("HOTSPOT_LLM_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leave")
    monkeypatch.setattr(G.httpx, "AsyncClient", _RecordingClient)
    _RecordingClient.calls = []

    svc = G.LLMService.__new__(G.LLMService)

    def _cfg(base_url):
        return ProviderConfig(
            type="openai", api_key_env="OPENAI_API_KEY",
            base_url=base_url, models={}, timeout_seconds=5,
        )

    async def _run():
        with pytest.raises(EgressNotAllowedError):
            await svc._call_openai(_cfg("https://evil.example.net/v1"), "gpt-x", "机密 prompt")
        assert _RecordingClient.calls == [], "恶意主机不应收到任何请求"
        out = await svc._call_openai(_cfg("https://api.openai.com/v1"), "gpt-x", "正常 prompt")
        assert out == "ok"
        return _RecordingClient.calls[-1]

    url, hdrs = asyncio.run(_run())
    assert url == "https://api.openai.com/v1/chat/completions"
    assert hdrs.get("Authorization") == "Bearer sk-should-not-leave", "白名单主机不得被误伤"

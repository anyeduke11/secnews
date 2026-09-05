"""v0.8.1 Day 3 — ai_hub 弹性接线 failover 测试 (PRD §2.2 / PLAN §2.3 D3)。

gateway: breaker 前置跳过 (拒绝 ≠ 失败, 不计账) + _call_provider 成败集中记账
+ unhealthy 自动 trip + 探针恢复; image_service: 直连点 breaker 前置快速失败 +
_record 全路径回写 (审查 P0-2 数据闭环)。

ProviderHealth 单例每测复位; OPEN 到期探针用 env RECOVERY_TIMEOUT=0.05 + 小睡。
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from backend.config.llm_schema import (
    CacheConfig,
    CostAlert,
    LLMConfig,
    ProviderConfig,
    ProviderModels,
    RateLimits,
)
from backend.services.ai_hub.gateway import LLMService
from backend.services.ai_hub.image_service import (
    ImageGenerationError,
    ImageGenerationService,
)
from backend.services.ai_hub.provider_health import (
    get_provider_health,
    reset_provider_health,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mk_provider(name: str) -> ProviderConfig:
    """三 provider 三种 type → 各自独立 mock 点 (_call_openai/_call_anthropic/_call_ollama)。

    不能同 type: 同名方法 setattr 会互相覆盖, per-provider closure 失效。
    """
    if name == "a":
        return ProviderConfig(type="openai", api_key_env="A_KEY", models=ProviderModels())
    if name == "b":
        return ProviderConfig(
            type="anthropic", api_key_env="B_KEY", models=ProviderModels()
        )
    return ProviderConfig(
        type="ollama", base_url="http://127.0.0.1:11434", models=ProviderModels()
    )


def _make_svc(
    monkeypatch: pytest.MonkeyPatch,
    providers: tuple[str, ...] = ("a", "b"),
    behavior: dict[str, str] | None = None,
    calls: list | None = None,
) -> LLMService:
    """构造 LLMService: mock 下层 per-type 调用 (_call_openai/_call_ollama)。

    不能 mock _call_provider 本体 — 那会绕过 Day 3 接线的真实记账路径。
    behavior: provider -> 'ok' | 'fail'; calls 记录实际被调 provider 序列。
    """
    cfg = LLMConfig(
        enabled=True,
        default_provider=providers[0],
        fallback_order=list(providers),
        providers={p: _mk_provider(p) for p in providers},
        cache=CacheConfig(enabled=False, ttl_seconds=1),
        cost_alert=CostAlert(),
        rate_limits=RateLimits(),
    )

    monkeypatch.setattr(
        "backend.services.ai_hub.gateway.load_llm_config", lambda _path=None: cfg
    )
    svc = LLMService()
    behavior = behavior or {}

    def _mk(name: str, behv: str):
        async def fake(*args, **kwargs):
            if calls is not None:
                calls.append(name)
            if behv == "fail":
                raise RuntimeError(f"{name} down")
            return "RAW"

        return fake

    for p in providers:
        method_name = {
            "a": "_call_openai", "b": "_call_anthropic", "c": "_call_ollama",
            "openai": "_call_openai", "anthropic": "_call_anthropic",
            "ollama": "_call_ollama", "sensenova": "_call_openai_compatible",
        }[p]
        monkeypatch.setattr(svc, method_name, _mk(p, behavior.get(p, "ok")))
    return svc


@pytest.fixture
def health(monkeypatch):
    """每测复位单例 + 缩短 RECOVERY_TIMEOUT (探针测试免等 30s)。"""
    reset_provider_health()
    monkeypatch.setenv("HOTSPOT_BREAKER_RECOVERY_TIMEOUT", "0.05")
    reset_provider_health()
    yield get_provider_health()
    reset_provider_health()


def _trip(health, provider: str) -> None:
    health.get_breaker(provider).trip()


# ===========================================================================
# gateway 接线
# ===========================================================================
class TestGatewayWiring:
    def test_success_records_ok(self, temp_db, monkeypatch, health):
        calls: list = []
        svc = _make_svc(monkeypatch, providers=("a",), behavior={"a": "ok"}, calls=calls)
        asyncio.run(svc.score("content-1"))
        snap = health.snapshot("a")
        assert snap["windows"]["1m"]["total"] == 1
        assert snap["windows"]["1m"]["failures"] == 0
        assert snap["breaker"]["state"] == "closed"

    def test_failure_records_and_falls_through(self, temp_db, monkeypatch, health):
        calls: list = []
        svc = _make_svc(
            monkeypatch, providers=("a", "b"),
            behavior={"a": "fail", "b": "ok"}, calls=calls,
        )
        asyncio.run(svc.score("content-2"))
        assert calls == ["a", "b"]
        snap = health.snapshot("a")
        assert snap["windows"]["1m"]["failures"] == 1
        assert snap["windows"]["1m"]["total"] == 1

    def test_open_provider_skipped_without_call_or_record(self, temp_db, monkeypatch, health):
        """OPEN 期: 不调用、不计账 (拒绝 ≠ 失败) — 审查 P0-1 关键语义。"""
        calls: list = []
        svc = _make_svc(monkeypatch, providers=("a", "b"), behavior={"b": "ok"}, calls=calls)
        _trip(health, "a")
        asyncio.run(svc.score("content-3"))
        assert calls == ["b"]  # a 被跳过
        assert health.snapshot("a")["windows"]["1m"]["total"] == 0  # 零记账
        assert health.snapshot("b")["windows"]["1m"]["total"] == 1

    def test_all_open_returns_default_no_calls(self, temp_db, monkeypatch, health):
        calls: list = []
        svc = _make_svc(monkeypatch, providers=("a", "b"), behavior={}, calls=calls)
        _trip(health, "a")
        _trip(health, "b")
        result = asyncio.run(svc.score("content-4"))
        assert calls == []
        assert result == 5.0  # DEFAULT_SCORE

    def test_unhealthy_verdict_auto_trips_mid_stream(self, temp_db, monkeypatch, health):
        """连续失败达窗口判定 → breaker 自动 OPEN → 后续调用直接跳过。"""
        calls: list = []
        svc = _make_svc(
            monkeypatch, providers=("a", "b"),
            behavior={"a": "fail", "b": "ok"}, calls=calls,
        )
        for i in range(4):  # 4 次 score, 每次 a fail + b ok
            asyncio.run(svc.score(f"content-{i}"))
        assert health.get_breaker("a").state == "open"  # 4 失败 ≥ min_samples 且 100%
        before = len(calls)
        asyncio.run(svc.score("content-final"))
        assert calls[before:] == ["b"]  # a 已被跳过

    def test_probe_success_recovers(self, temp_db, monkeypatch, health):
        calls: list = []
        svc = _make_svc(monkeypatch, providers=("a", "b"), behavior={"a": "ok", "b": "ok"}, calls=calls)
        _trip(health, "a")
        time.sleep(0.06)  # RECOVERY_TIMEOUT=0.05 到期
        asyncio.run(svc.score("content-5"))
        assert calls[0] == "a"  # 探针授予给 a
        assert health.get_breaker("a").state == "closed"  # 探针成功 → 闭合

    def test_probe_failure_reopens(self, temp_db, monkeypatch, health):
        calls: list = []
        svc = _make_svc(
            monkeypatch, providers=("a", "b"),
            behavior={"a": "fail", "b": "ok"}, calls=calls,
        )
        _trip(health, "a")
        time.sleep(0.06)
        asyncio.run(svc.score("content-6"))
        assert calls == ["a", "b"]  # 探针 a 失败 → 落到 b
        assert health.get_breaker("a").state == "open"  # 探针失败 → 重回 OPEN

    def test_wiring_shared_across_tasks(self, temp_db, monkeypatch, health):
        """score / summarize / generate 共用同一 provider 窗口与 breaker。"""
        calls: list = []
        svc = _make_svc(monkeypatch, providers=("a",), behavior={"a": "ok"}, calls=calls)
        asyncio.run(svc.score("c1"))
        asyncio.run(svc.summarize(["c2"]))
        asyncio.run(svc.generate("c3", task="deep_read"))
        snap = health.snapshot("a")
        assert snap["windows"]["1m"]["total"] == 3


# ===========================================================================
# image_service 直连点接入 (审查 P0-2 闭环)
# ===========================================================================
def _image_svc() -> ImageGenerationService:
    svc = ImageGenerationService()
    ai = MagicMock()
    ai._resolve_api_key.return_value = "test-key"
    ai._key_source.return_value = "env"
    ai._base_url.return_value = "https://token.sensenova.cn/v1"
    ai._config_source.return_value = "default"
    svc._ai = ai
    return svc


class TestImageWiring:
    def test_breaker_rejected_fast_no_http_no_record(self, temp_db, monkeypatch, health):
        """OPEN 期: 图片路径快速失败, 不发 HTTP、不计账 (拒绝 ≠ 失败)。"""
        svc = _image_svc()
        _trip(health, "sensenova")
        post_calls: list = []

        async def fake_post(*a, **kw):
            post_calls.append(1)
            return MagicMock()

        with patch.object(httpx.AsyncClient, "post", new=fake_post):
            with pytest.raises(ImageGenerationError, match="熔断中"):
                asyncio.run(svc.generate("a cat"))
        assert post_calls == []
        assert health.snapshot("sensenova")["windows"]["1m"]["total"] == 0

    def test_image_success_records_health(self, temp_db, monkeypatch, health):
        svc = _image_svc()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"url": "https://img.example/x.png"}]}

        async def fake_post(*a, **kw):
            return mock_resp

        with patch.object(svc, "_ai", _image_svc()._ai), \
             patch.object(httpx.AsyncClient, "post", new=fake_post):
            result = asyncio.run(svc.generate("a cat"))
        assert result["ok"] is True
        snap = health.snapshot("sensenova")
        assert snap["windows"]["1m"]["total"] == 1
        assert snap["windows"]["1m"]["failures"] == 0

    def test_image_timeout_records_failure(self, temp_db, monkeypatch, health):
        svc = _image_svc()

        async def fake_post(*a, **kw):
            raise httpx.TimeoutException("read timed out")

        with patch.object(svc, "_ai", _image_svc()._ai), \
             patch.object(httpx.AsyncClient, "post", new=fake_post):
            with pytest.raises(ImageGenerationError, match="上游超时"):
                asyncio.run(svc.generate("a cat"))
        snap = health.snapshot("sensenova")
        assert snap["windows"]["1m"]["failures"] == 1

    def test_image_understand_wired_too(self, temp_db, monkeypatch, health):
        """understand (第二直连点) 同样记账 — 审查 P0-2 双点闭环。"""
        svc = _image_svc()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "desc"}}]}

        async def fake_post(*a, **kw):
            return mock_resp

        with patch.object(svc, "_ai", _image_svc()._ai), \
             patch.object(httpx.AsyncClient, "post", new=fake_post):
            result = asyncio.run(svc.understand("aGVsbG8=", "describe"))
        assert result["ok"] is True
        assert health.snapshot("sensenova")["windows"]["1m"]["total"] == 1

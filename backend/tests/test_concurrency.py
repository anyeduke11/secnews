"""v0.8.2 Y-A1 — 全局并发单一真相源单元 + gateway 接入测试 (CRITICAL_REVIEW §1.1)。

契约: (group, loop) 键控共享 Semaphore / size 首次生效 / env 覆盖 /
等待即背压 (饱和不驱动 breaker) / gateway llm:<provider> 组强制执行
llm.yaml max_concurrent (此前声明但零消费)。
"""

from __future__ import annotations

import asyncio

from backend.utils.concurrency import (
    DEFAULT_SIZE,
    get_semaphore,
    registry_snapshot,
    reset_concurrency,
)


class TestRegistry:
    def setup_method(self):
        reset_concurrency()

    def test_same_group_same_instance(self):
        async def main():
            s1 = get_semaphore("enrich")
            s2 = get_semaphore("enrich")
            assert s1 is s2
            s3 = get_semaphore("url_check")
            assert s3 is not s1

        asyncio.run(main())

    def test_explicit_size_first_wins(self):
        async def main():
            s1 = get_semaphore("enrich", size=7)
            s2 = get_semaphore("enrich", size=2)  # 首次定容, 后续实参仅声明
            assert s1 is s2
            assert registry_snapshot()["enrich"] == 7

        asyncio.run(main())

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("HOTSPOT_CONCURRENCY_URL_CHECK", "9")
        async def main():
            get_semaphore("url_check")
            assert registry_snapshot()["url_check"] == 9

        asyncio.run(main())

    def test_default_size(self):
        async def main():
            get_semaphore("no-default-group")
            assert registry_snapshot()["no-default-group"] == DEFAULT_SIZE == 4

        asyncio.run(main())

    def test_env_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("HOTSPOT_CONCURRENCY_ENRICH", "abc")
        async def main():
            get_semaphore("enrich")
            assert registry_snapshot()["enrich"] == DEFAULT_SIZE

        asyncio.run(main())

    def test_loop_isolation(self):
        """asyncio 原语不可跨 loop — registry 按 loop 键控, 各 loop 独立实例。"""
        async def one():
            return get_semaphore("enrich", size=2)

        s1 = asyncio.run(one())
        s2 = asyncio.run(one())
        assert s1 is not s2

    def test_no_running_loop_creates_placeholder(self):
        """同步上下文 (无 running loop) 也可取 — loop_id=0 占位键。"""
        s1 = get_semaphore("enrich", size=3)
        s2 = get_semaphore("enrich")
        assert s1 is s2

    def test_limits_actual_concurrency(self):
        """semaphore size=2: 5 个并发协程的瞬时重叠峰值 == 2。"""
        async def main():
            sem = get_semaphore("url_check", size=2)
            in_flight = 0
            peak = 0

            async def worker():
                nonlocal in_flight, peak
                async with sem:
                    in_flight += 1
                    peak = max(peak, in_flight)
                    await asyncio.sleep(0.01)
                    in_flight -= 1

            await asyncio.gather(*(worker() for _ in range(5)))
            assert peak == 2

        asyncio.run(main())


class TestGatewayIntegration:
    def setup_method(self):
        reset_concurrency()

    def test_llm_provider_semaphore_enforced(self, monkeypatch):
        """max_concurrent=1 的 provider: 并发两请求 → 瞬时重叠峰值 == 1。

        mock 下层 per-type 方法 (不 mock _call_provider, 保住记账/背压真实路径)。
        """
        from backend.config.llm_schema import (
            CacheConfig,
            CostAlert,
            LLMConfig,
            ProviderConfig,
            ProviderModels,
            RateLimits,
        )
        from backend.services.ai_hub.gateway import LLMService

        cfg = LLMConfig(
            enabled=True,
            default_provider="a",
            fallback_order=["a"],
            providers={
                "a": ProviderConfig(
                    type="openai", api_key_env="A_KEY",
                    models=ProviderModels(), max_concurrent=1,
                )
            },
            cache=CacheConfig(enabled=False, ttl_seconds=1),
            cost_alert=CostAlert(),
            rate_limits=RateLimits(),
        )
        monkeypatch.setattr(
            "backend.services.ai_hub.gateway.load_llm_config", lambda _path=None: cfg
        )
        svc = LLMService()

        in_flight = 0
        peak = 0

        async def fake_openai(*args, **kwargs):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return "RAW"

        monkeypatch.setattr(svc, "_call_openai", fake_openai)

        async def main():
            await asyncio.gather(
                svc._call_provider(cfg.providers["a"], "m", "p", provider_name="a"),
                svc._call_provider(cfg.providers["a"], "m", "p", provider_name="a"),
            )
            assert peak == 1
            assert registry_snapshot()["llm:a"] == 1

        asyncio.run(main())

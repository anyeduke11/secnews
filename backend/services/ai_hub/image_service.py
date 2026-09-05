"""图片生成 + 视觉理解服务 (v0.7.4-image).

不复用 LLMService.score/summarize 循环 (避免污染 chat completions 路径)。
复用 AIService 单点四级链 (凭据解析与密钥打标走 Batch ⑥ 已落路径)。
观测面: 每次调用走 ``record_llm_call`` → ``llm_usage_log`` 写一条 (scene=image_generation / image_understand).

模型选择: ``scenarios.resolve_scenario_model(Scenario.IMAGE)`` → ScenarioRoute.
endpoint 区分:
- generate() → /v1/images/generations  (sensenova-u1.5-lite 文生图)
- understand() → /chat/completions  (sensenova-u1.5-lite 多模态, image_url 携 data URI)
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from backend.logging_config import logger

from .provider_health import get_provider_health
from .scenarios import Scenario, resolve_scenario_model


class ImageGenerationError(Exception):
    """图片生成/理解流程失败 (provider不可达 / 4xx/5xx / 解析失败 / 凭据空)."""


class ImageGenerationService:
    """sensenova-u1.5-lite 文生图 + 多模态图理解。"""

    DEFAULT_SIZE = "1024x1024"
    DEFAULT_N = 1
    REQUEST_TIMEOUT_S = 60.0  # 公测期实测 P95<20s, 60s 兜底
    MAX_PROMPT_LEN = 4000
    MAX_IMAGE_B64_LEN = 8 * 1024 * 1024  # 8MB base64 ≈ 6MB 二进制, 与 sensenova 文档一致

    def __init__(self) -> None:
        # AIService 单点 — _resolve_api_key / _key_source 走 Batch ⑥ 已落四级链
        from backend.services.ai_hub.service import AIService
        self._ai = AIService()

    async def generate(
        self,
        prompt: str,
        *,
        size: str = DEFAULT_SIZE,
        n: int = DEFAULT_N,
        watermark: bool = False,
        scenario: Scenario = Scenario.IMAGE,
    ) -> dict[str, Any]:
        """文生图: POST /v1/images/generations。

        Returns ``{"ok": True, "images": [{url, b64_json}], "provider", "model", "latency_ms"}``。
        公测期 watermark=false 免费 (官方明示); watermark=true 才计费。
        """
        prompt = (prompt or "").strip()
        if not prompt:
            raise ImageGenerationError("prompt 不能为空")
        if len(prompt) > self.MAX_PROMPT_LEN:
            raise ImageGenerationError(
                f"prompt 超长 ({len(prompt)} > {self.MAX_PROMPT_LEN})"
            )

        route = resolve_scenario_model(scenario)
        provider = "sensenova"
        # v0.8.1 Day 3: breaker 前置检查 — OPEN 期快速失败 (拒绝不计账)。
        # allow() 在 OPEN 到期时授予探针 → 图片路径参与熔断恢复探测 (审查 P0-2)。
        breaker = get_provider_health().get_breaker(provider)
        if not breaker.allow():
            raise ImageGenerationError(
                f"provider={provider} 熔断中 (breaker={breaker.state}), 稍后重试"
            )
        key = self._ai._resolve_api_key(provider)
        if not key:
            raise ImageGenerationError(
                f"provider={provider} 凭据为空 (key_source={self._ai._key_source(provider)})"
            )

        url = self._ai._base_url(provider) + route.endpoint
        payload = {
            "model": route.model,
            "prompt": prompt,
            "size": size,
            "n": n,
            "watermark": watermark,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT_S) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            self._record(provider, route.model, "image_generation", ok=False,
                         error=f"TimeoutException: {e}",
                         latency_ms=(time.monotonic() - t0) * 1000)
            raise ImageGenerationError(f"上游超时: {e}") from e
        except httpx.HTTPError as e:
            self._record(provider, route.model, "image_generation", ok=False,
                         error=f"{type(e).__name__}: {e}",
                         latency_ms=(time.monotonic() - t0) * 1000)
            raise ImageGenerationError(f"网络错误: {e}") from e

        latency_ms = (time.monotonic() - t0) * 1000
        if resp.status_code >= 400:
            self._record(provider, route.model, "image_generation", ok=False,
                         error=f"HTTP {resp.status_code}: {resp.text[:300]}",
                         latency_ms=latency_ms)
            raise ImageGenerationError(
                f"sensenova {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        images = data.get("data") or data.get("images") or []
        self._record(provider, route.model, "image_generation", ok=True,
                     prompt=prompt, response=str(images)[:300],
                     latency_ms=latency_ms)
        return {
            "ok": True,
            "images": images,
            "provider": provider,
            "model": route.model,
            "latency_ms": int(latency_ms),
        }

    async def understand(
        self,
        image_b64: str,
        prompt: str,
        *,
        scenario: Scenario = Scenario.IMAGE,
    ) -> dict[str, Any]:
        """多模态图理解: POST /v1/chat/completions 携 image_url (data URI).

        Returns ``{"ok": True, "text": "...", "provider", "model", "latency_ms"}``.
        """
        if not image_b64 or not prompt:
            raise ImageGenerationError("image_b64 与 prompt 均必填")
        if len(image_b64) > self.MAX_IMAGE_B64_LEN:
            raise ImageGenerationError(
                f"image_b64 超 {self.MAX_IMAGE_B64_LEN // (1024 * 1024)}MB 上限"
            )

        route = resolve_scenario_model(scenario)
        provider = "sensenova"
        # v0.8.1 Day 3: breaker 前置检查 (同 generate — 审查 P0-2 图片路径闭环)
        breaker = get_provider_health().get_breaker(provider)
        if not breaker.allow():
            raise ImageGenerationError(
                f"provider={provider} 熔断中 (breaker={breaker.state}), 稍后重试"
            )
        key = self._ai._resolve_api_key(provider)
        if not key:
            raise ImageGenerationError(
                f"provider={provider} 凭据为空 (key_source={self._ai._key_source(provider)})"
            )

        url = self._ai._base_url(provider) + "/chat/completions"
        payload = {
            "model": route.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            "max_tokens": 600,
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT_S) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            self._record(provider, route.model, "image_understand", ok=False,
                         error=f"TimeoutException: {e}",
                         latency_ms=(time.monotonic() - t0) * 1000)
            raise ImageGenerationError(f"上游超时: {e}") from e

        latency_ms = (time.monotonic() - t0) * 1000
        if resp.status_code >= 400:
            self._record(provider, route.model, "image_understand", ok=False,
                         error=f"HTTP {resp.status_code}: {resp.text[:300]}",
                         latency_ms=latency_ms)
            raise ImageGenerationError(
                f"sensenova {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        self._record(provider, route.model, "image_understand", ok=True,
                     prompt=prompt, response=text[:300], latency_ms=latency_ms)
        return {
            "ok": True,
            "text": text,
            "provider": provider,
            "model": route.model,
            "latency_ms": int(latency_ms),
        }

    def _record(self, provider: str, model: str, task: str, *, ok: bool, **kw) -> None:
        """观测写入 — 走既有 record_llm_call, scene 区分 image_generation/image_understand.

        v0.8.1 Day 3: 同时回写 ProviderHealth (generate/understand 两处
        httpx 直连点的全部成败路径都经此 — 审查 P0-2 数据闭环)。
        """
        try:
            get_provider_health().record(provider, ok)
        except Exception as e:
            logger.warning(f"provider health record failed (ignored): {e}")
        try:
            from backend.services.ai_hub.usage import record_llm_call
            record_llm_call(
                provider=provider, model=model, task=task,
                ok=ok,
                prompt=kw.get("prompt", ""),
                response=kw.get("response", ""),
                error=kw.get("error", ""),
                latency_ms=kw.get("latency_ms", 0),
                scene=task,
                config_source=self._ai._config_source(),
                key_source=self._ai._key_source(provider),
            )
        except Exception as e:
            logger.debug("image_service._record swallow: %s", e)


__all__ = ["ImageGenerationError", "ImageGenerationService"]

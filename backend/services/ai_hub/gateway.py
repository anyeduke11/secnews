"""ai_hub/gateway.py — LLM 网关: 多 provider 调用 + 路由 + 缓存/用量委托 (v0.7+ 拆分)。

v0.7+ 拆分: 原 gateway.py (406 行) 拆为:
- ``gateway.py``     (本文件, ~260 行) — ``LLMService`` 类 (构造 / config / provider 解析 /
  4 任务循环 / provider 调用 / 模型+key 解析)
- ``prompts.py``     (~110 行) — 无状态工具: prompt 构造 + LLM 响应解析 + 缓存 key
- ``cache.py`` / ``usage.py`` — 数据面 (DB 投影)

向后兼容: ``from backend.services.ai_hub import llm_service, LLMService, DEFAULT_SCORE,
COST_PER_1M_TOKENS`` 仍可解析 (由 ``__init__.py`` re-export).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from backend.config.llm_schema import LLMConfig, ProviderConfig, load_llm_config

from .cache import get_llm_cache, set_llm_cache
from .egress import check_credential_egress
from .prompts import (
    COST_PER_1M_TOKENS,  # noqa: F401  -- 由 __init__.py 从本模块再导出, 保 `from backend.services.ai_hub import COST_PER_1M_TOKENS`
    DEFAULT_SCORE,
    _build_extract_entities_prompt,
    _build_score_prompt,
    _build_summary_prompt,
    _estimate_cost,
    _make_cache_key,
    _parse_entity_list,
    _parse_score,
)
from .usage import log_llm_usage

log = logging.getLogger("hotspot.ai_hub")


class LLMService:
    """统一 LLM 入口，支持多 provider + 降级 + 缓存.

    Usage::

        from backend.services.ai_hub import llm_service

        score = await llm_service.score("article content", "h-123")
        summary = await llm_service.summarize(["chunk1", "chunk2"])
    """

    def __init__(
        self,
        config_path: Path | None = None,
    ):
        self._config: LLMConfig | None = load_llm_config(config_path)
        if self._config is None:
            log.info("LLM config not found, running in v1.7 compatibility mode")
        else:
            log.info(
                "LLMService initialized: default=%s, fallback=%s",
                self._config.default_provider,
                self._config.fallback_order,
            )

    # ── Public API ────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        """是否启用 LLM 功能."""
        return self._config is not None and self._config.enabled

    @property
    def config(self) -> LLMConfig | None:
        return self._config

    def resolve_provider_for_task(self, task: str) -> tuple[str, str] | None:
        """S4-1: 委托 ``model_router.route_model`` 返回 (provider, model)。

        返回 None 时表示 router 不可用 (LLM 未启用或 import 失败), 调用方
        走原有 fallback_order 兜底链; 此时行为完全等价于 S4-1 之前的实现。
        """
        if not self.enabled or self._config is None:
            return None
        try:
            from backend.services.llm.model_router import route_model
            return route_model(task, config=self._config)
        except Exception as e:
            log.warning(f"resolve_provider_for_task({task}) failed: {e}")
            return None

    def _try_order(self, task_attr: str) -> list[str]:
        """S4-1: 拼接"router 优先 + fallback_order 兜底"的尝试列表。

        首位插入 router 推荐的 provider; 后续 fallback_order 元素去重保留,
        行为不变 (router 推荐失败 → fallback_order 全部仍然尝试)。
        """
        routed = self.resolve_provider_for_task(task_attr)
        order: list[str] = []
        if routed is not None:
            pname = routed[0]
            if pname in self._config.providers:
                order.append(pname)
        for p in self._config.fallback_order:
            if p not in order:
                order.append(p)
        return order

    async def score(self, content: str, hotspot_id: str = "") -> float:
        """T1 评分，返回 0~10.

        按 fallback_order 依次尝试 provider，全部失败时返回 DEFAULT_SCORE (5.0)。
        S4-1: router 推荐的 provider 作为首位优先尝试, 失败后兜底链不变。
        """
        if not self.enabled:
            return DEFAULT_SCORE

        cache_key = _make_cache_key("score", content)
        cached = get_llm_cache(cache_key)
        if cached is not None:
            try:
                return float(cached)
            except (TypeError, ValueError):
                pass

        for provider_name in self._try_order("score"):
            try:
                cfg = self._config.providers[provider_name]
                model = self._resolve_model(provider_name, "score")
                prompt = _build_score_prompt(content)
                raw = await self._call_provider(cfg, model, prompt)
                score = _parse_score(raw)
                set_llm_cache(cache_key, str(score))
                log_llm_usage(provider_name, model, "score", prompt, raw)
                return score
            except Exception as e:
                log.warning("Provider %s score failed: %s", provider_name, e)
                continue

        log.info("All LLM providers failed, falling back to default score")
        return DEFAULT_SCORE

    async def summarize(self, chunks: list[str]) -> str:
        """T3 摘要，返回汇总文本.

        优先用本地 LLM（Ollama）批量处理，失败时降级。
        """
        if not self.enabled:
            return ""

        text = "\n\n".join(chunks) if isinstance(chunks, list) else chunks
        cache_key = _make_cache_key("summary", text)
        cached = get_llm_cache(cache_key)
        if cached is not None:
            return cached

        for provider_name in self._try_order("summary"):
            try:
                cfg = self._config.providers[provider_name]
                model = self._resolve_model(provider_name, "summary")
                prompt = _build_summary_prompt(text)
                raw = await self._call_provider(cfg, model, prompt)
                set_llm_cache(cache_key, raw)
                log_llm_usage(provider_name, model, "summarize", prompt, raw)
                return raw
            except Exception as e:
                log.warning("Provider %s summarize failed: %s", provider_name, e)
                continue

        # 降级：返回前 200 字符
        log.info("All LLM providers failed for summarize, using truncation")
        return text[:200]

    async def extract_entities(self, content: str) -> list[str]:
        """T1 实体提取."""
        if not self.enabled:
            return []

        cache_key = _make_cache_key("entities", content)
        cached = get_llm_cache(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, TypeError):
                pass

        for provider_name in self._try_order("ner"):
            try:
                cfg = self._config.providers[provider_name]
                model = self._resolve_model(provider_name, "ner")
                prompt = _build_extract_entities_prompt(content)
                raw = await self._call_provider(cfg, model, prompt)
                entities = _parse_entity_list(raw)
                set_llm_cache(cache_key, json.dumps(entities))
                log_llm_usage(provider_name, model, "extract_entities", prompt, raw)
                return entities
            except Exception as e:
                log.warning("Provider %s extract_entities failed: %s", provider_name, e)
                continue

        return []

    async def generate(self, prompt: str) -> str:
        """通用生成接口."""
        if not self.enabled:
            return ""

        for provider_name in self._try_order("summary"):
            try:
                cfg = self._config.providers[provider_name]
                model = self._resolve_model(provider_name, "summary")
                raw = await self._call_provider(cfg, model, prompt)
                log_llm_usage(provider_name, model, "generate", prompt, raw)
                return raw
            except Exception as e:
                log.warning("Provider %s generate failed: %s", provider_name, e)
                continue

        return ""

    # ── Provider 调用 ─────────────────────────────────────────────

    async def _call_provider(
        self, cfg: ProviderConfig, model: str, prompt: str
    ) -> str:
        """调用指定 provider 的 LLM API."""
        t0 = time.monotonic()

        if cfg.type == "ollama":
            result = await self._call_ollama(cfg, model, prompt)
        elif cfg.type == "openai":
            result = await self._call_openai(cfg, model, prompt)
        elif cfg.type == "openai_compatible":
            result = await self._call_openai_compatible(cfg, model, prompt)
        elif cfg.type == "anthropic":
            result = await self._call_anthropic(cfg, model, prompt)
        else:
            raise ValueError(f"Unsupported provider type: {cfg.type}")

        elapsed_ms = (time.monotonic() - t0) * 1000
        log.debug("LLM call %s/%s: %dms", cfg.type, model, int(elapsed_ms))
        return result

    async def _call_ollama(self, cfg: ProviderConfig, model: str, prompt: str) -> str:
        """调用 Ollama API."""
        base_url = cfg.base_url or "http://127.0.0.1:11434"
        url = f"{base_url.rstrip('/')}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 100},
        }
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")

    async def _call_openai(self, cfg: ProviderConfig, model: str, prompt: str) -> str:
        """调用 OpenAI API."""
        api_key = self._get_api_key(cfg.api_key_env)
        base_url = cfg.base_url or "https://api.openai.com/v1"
        # C3: 凭据只允许发往代码侧白名单主机 (base_url 可被同步包写入 llm.yaml)
        check_credential_egress(base_url)
        url = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _call_openai_compatible(
        self, cfg: ProviderConfig, model: str, prompt: str
    ) -> str:
        """调用兼容 OpenAI API 的 provider（如 Qwen）. """
        return await self._call_openai(cfg, model, prompt)

    async def _call_anthropic(
        self, cfg: ProviderConfig, model: str, prompt: str
    ) -> str:
        """调用 Anthropic API."""
        api_key = self._get_api_key(cfg.api_key_env)
        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": model,
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

    # ── 辅助方法 ──────────────────────────────────────────────────

    def _resolve_model(self, provider_name: str, task: str) -> str:
        """解析任务对应的模型名."""
        cfg = self._config.providers[provider_name]
        model_map = {
            "score": cfg.models.score,
            "summarize": cfg.models.summary,
            "ner": cfg.models.ner,
            "tag": cfg.models.tag,
            "chunk_summary": cfg.models.chunk_summary,
        }
        return model_map.get(task, cfg.models.score)

    @staticmethod
    def _get_api_key(env_var: str | None) -> str:
        """从环境变量读取 API key."""
        if not env_var:
            return ""
        import os
        key = os.environ.get(env_var, "")
        if not key:
            log.warning("API key env var %s not set", env_var)
        return key

    # ── 静态方法委托 (向后兼容: 旧测试 LLMService._parse_score 等) ───
    # v0.7 拆分后内部实现移至 prompts.py, 类方法仅作委托.
    @staticmethod
    def _parse_score(raw: str) -> float:
        """[委托] 从 LLM 响应中解析评分."""
        return _parse_score(raw)

    @staticmethod
    def _parse_entity_list(raw: str) -> list[str]:
        """[委托] 从 LLM 响应中解析实体列表."""
        return _parse_entity_list(raw)

    @staticmethod
    def _build_score_prompt(content: str) -> str:
        """[委托] 构建评分 prompt."""
        return _build_score_prompt(content)

    @staticmethod
    def _build_summary_prompt(text: str) -> str:
        """[委托] 构建摘要 prompt."""
        return _build_summary_prompt(text)

    @staticmethod
    def _make_cache_key(prefix: str, content: str) -> str:
        """[委托] 生成缓存 key."""
        return _make_cache_key(prefix, content)

    @staticmethod
    def _estimate_cost(model: str, tokens: int) -> float:
        """[委托] 估算 LLM 调用 USD 成本."""
        return _estimate_cost(model, tokens)


# 全局单例
llm_service = LLMService()

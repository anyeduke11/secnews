"""ai_hub/gateway.py — LLM 网关：多 provider 调用 + 路由 + 缓存/用量委托。

职责
----
- ``LLMService``: score / summarize / extract_entities / generate 四条主路径
- provider 分发: ollama / openai / openai_compatible / anthropic
- 路由委托: ``resolve_provider_for_task`` 委托 ``model_router.route_model``
- 缓存委托: ``_get_cached`` / ``_set_cache`` → ``ai_hub.cache``
- 用量委托: ``_log_usage`` → ``ai_hub.usage``
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import httpx

from backend.config.llm_schema import LLMConfig, ProviderConfig, load_llm_config

from .cache import get_llm_cache, set_llm_cache
from .usage import log_llm_usage

log = logging.getLogger("hotspot.ai_hub")

# 默认评分兜底 (score 0-10)
DEFAULT_SCORE = 5.0

# 成本估算 (USD per 1M tokens) — 近似值
COST_PER_1M_TOKENS: dict[str, float] = {
    "gpt-4o-mini": 0.15,
    "gpt-4o": 5.0,
    "qwen-turbo": 0.3,
    "qwen-plus": 0.8,
    "claude-3-5-haiku-20241022": 0.8,
    "claude-3-5-sonnet-20241022": 3.0,
    # Ollama 本地模型零成本
}


def _estimate_cost(model: str, tokens: int) -> float:
    """估算一次 LLM 调用的 USD 成本."""
    if tokens <= 0:
        return 0.0
    rate = COST_PER_1M_TOKENS.get(model, 0.5)  # 默认 $0.5/1M
    return (tokens / 1_000_000) * rate


def _make_cache_key(prefix: str, content: str) -> str:
    """生成缓存 key: {prefix}:{sha256(content)[:16]}."""
    h = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"{prefix}:{h}"


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
                prompt = self._build_score_prompt(content)
                raw = await self._call_provider(cfg, model, prompt)
                score = self._parse_score(raw)
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
                prompt = self._build_summary_prompt(text)
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
                prompt = (
                    "Extract named entities (person/company/technology/product) "
                    f"from the following text. Return as a JSON list of strings:\n\n{content}"
                )
                raw = await self._call_provider(cfg, model, prompt)
                entities = self._parse_entity_list(raw)
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

    @staticmethod
    def _build_score_prompt(content: str) -> str:
        """构建评分 prompt."""
        MAX_LEN = 2000
        truncated = content[:MAX_LEN]
        return (
            "Rate the following article on a scale of 0.0 to 10.0 based on its "
            "relevance to AI and cybersecurity. Consider: technical depth, novelty, "
            "practical applicability. Return ONLY a number between 0 and 10.\n\n"
            f"Article:\n{truncated}"
        )

    @staticmethod
    def _build_summary_prompt(text: str) -> str:
        """构建摘要 prompt."""
        MAX_LEN = 4000
        truncated = text[:MAX_LEN]
        return (
            "Summarize the following text in 2-3 sentences. "
            "Focus on key technical points and actionable insights.\n\n"
            f"{truncated}"
        )

    @staticmethod
    def _parse_score(raw: str) -> float:
        """从 LLM 响应中解析评分."""
        import re
        match = re.search(r"(\d+(?:\.\d+)?)", raw.strip())
        if match:
            val = float(match.group(1))
            return max(0.0, min(10.0, val))
        return DEFAULT_SCORE

    @staticmethod
    def _parse_entity_list(raw: str) -> list[str]:
        """从 LLM 响应中解析实体列表."""
        # 尝试 JSON 解析
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(e) for e in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        # 尝试行解析
        entities = []
        for line in raw.strip().split("\n"):
            line = line.strip().strip("- ").strip('"').strip("'")
            if line and not line.startswith("{"):
                entities.append(line)
        return entities[:20]  # 最多 20 个实体


# 全局单例
llm_service = LLMService()

"""ai_hub — LLM 单出口 + 知识写回唯一门面 (v0.5 M5 Task19)。

M5 Task19 把旧的 ``llm_service`` (LLMService 回退链) 与 ``ai_service``
(AIService 集中式凭据/缓存/限频/评分) 合并进本模块 —— 单 PR, 不搞 strangler。
全仓 LLM 调用只有一条入口: ``from backend.services.ai_hub import ...``。

职责分层 (v0.5):
- **LLM 能力**: ``LLMService`` (score/summarize/extract_entities/generate,
  多 provider 回退链) + ``AIService`` (evaluate/gate_detect, 凭据/缓存/限频/
  用量统一管理) + ``evaluate_article`` (评价入口)。
- **ai_scores 写路径**: ``write_score`` — 唯一向 ``ai_scores`` 表 INSERT 的
  生产入口 (SPEC §1 Task19: ai_scores 写路径仅 ai_hub 命中)。
- **知识写回**: ``write_item`` / ``update_frontmatter`` — items/*.md 结构化
  写回 + wiki_events 留痕 (§18.2 强约束 1: 知识写入唯一路径)。

事件语义 (write_item):
- kind: ``agent_write`` (系统/agent 写回) | ``cli_agent_run`` (§19 外部 CLI)
- agent: 产生者标识, 如 ``api:patch_item`` / ``job:stub_backfill`` /
  ``kl:compiler`` / ``trigger:t4`` / ``mcp:wiki_write``
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import httpx

from backend.config.llm_schema import LLMConfig, ProviderConfig, load_llm_config
from backend.logging_config import logger as _logger
from backend.repository.db import get_connection

log = logging.getLogger("hotspot.ai_hub")

# 默认评分兜底 (score 0-10 / confidence 用 0.5 见 write_item 侧)
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


# ═══════════════════════════════════════════════════════════════
# LLMService — 统一 LLM 入口 (多 provider + 降级 + 缓存)
# ═══════════════════════════════════════════════════════════════

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

    async def score(self, content: str, hotspot_id: str = "") -> float:
        """T1 评分，返回 0~10.

        按 fallback_order 依次尝试 provider，全部失败时返回 DEFAULT_SCORE (5.0)。
        """
        if not self.enabled:
            return DEFAULT_SCORE

        cache_key = _make_cache_key("score", content)
        cached = self._get_cached(cache_key)
        if cached is not None:
            try:
                return float(cached)
            except (TypeError, ValueError):
                pass

        for provider_name in self._config.fallback_order:
            try:
                cfg = self._config.providers[provider_name]
                model = self._resolve_model(provider_name, "score")
                prompt = self._build_score_prompt(content)
                raw = await self._call_provider(cfg, model, prompt)
                score = self._parse_score(raw)
                self._set_cache(cache_key, provider_name, model, str(score))
                self._log_usage(provider_name, model, "score", prompt, raw)
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
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        for provider_name in self._config.fallback_order:
            try:
                cfg = self._config.providers[provider_name]
                model = self._resolve_model(provider_name, "summary")
                prompt = self._build_summary_prompt(text)
                raw = await self._call_provider(cfg, model, prompt)
                self._set_cache(cache_key, provider_name, model, raw)
                self._log_usage(provider_name, model, "summarize", prompt, raw)
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
        cached = self._get_cached(cache_key)
        if cached is not None:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, TypeError):
                pass

        for provider_name in self._config.fallback_order:
            try:
                cfg = self._config.providers[provider_name]
                model = self._resolve_model(provider_name, "ner")
                prompt = (
                    "Extract named entities (person/company/technology/product) "
                    f"from the following text. Return as a JSON list of strings:\n\n{content}"
                )
                raw = await self._call_provider(cfg, model, prompt)
                entities = self._parse_entity_list(raw)
                self._set_cache(cache_key, provider_name, model, json.dumps(entities))
                self._log_usage(provider_name, model, "extract_entities", prompt, raw)
                return entities
            except Exception as e:
                log.warning("Provider %s extract_entities failed: %s", provider_name, e)
                continue

        return []

    async def generate(self, prompt: str) -> str:
        """通用生成接口."""
        if not self.enabled:
            return ""

        for provider_name in self._config.fallback_order:
            try:
                cfg = self._config.providers[provider_name]
                model = self._resolve_model(provider_name, "summary")
                raw = await self._call_provider(cfg, model, prompt)
                self._log_usage(provider_name, model, "generate", prompt, raw)
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

    # ── 缓存 ──────────────────────────────────────────────────────

    def _get_cached(self, cache_key: str) -> str | None:
        """从 SQLite 缓存读取."""
        if not self._config or not self._config.cache.enabled:
            return None
        try:
            conn = get_connection()
            row = conn.execute(
                "SELECT response, cached_at, ttl_seconds FROM llm_cache "
                "WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if row is None:
                return None
            # 检查 TTL
            cached_at = datetime.fromisoformat(row["cached_at"])
            ttl = row["ttl_seconds"]
            age = (datetime.now(timezone.utc) - cached_at).total_seconds()
            if age < ttl:
                return row["response"]
            # 过期删除
            conn.execute("DELETE FROM llm_cache WHERE cache_key = ?", (cache_key,))
            return None
        except Exception:
            return None

    def _set_cache(
        self, cache_key: str, provider: str, model: str, response: str
    ) -> None:
        """写入 SQLite 缓存."""
        if not self._config or not self._config.cache.enabled:
            return
        try:
            conn = get_connection()
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache "
                "(cache_key, provider, model, response, cached_at, ttl_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    cache_key,
                    provider,
                    model,
                    response,
                    datetime.now(timezone.utc).isoformat(),
                    self._config.cache.ttl_seconds,
                ),
            )
        except Exception:
            pass

    # ── 用量日志 ──────────────────────────────────────────────────

    def _log_usage(
        self,
        provider: str,
        model: str,
        task: str,
        prompt: str,
        response: str,
    ) -> None:
        """记录 LLM 调用用量."""
        try:
            prompt_tokens = len(prompt) // 4  # 粗略估算
            response_tokens = len(response) // 4
            total_tokens = prompt_tokens + response_tokens
            cost = _estimate_cost(model, total_tokens)

            conn = get_connection()
            conn.execute(
                "INSERT INTO llm_usage_log "
                "(provider, model, task, tokens, cost_usd, latency_ms, occurred_at) "
                "VALUES (?, ?, ?, ?, ?, 0, ?)",
                (provider, model, task, total_tokens, cost,
                 datetime.now(timezone.utc).isoformat()),
            )
        except Exception:
            pass


# 全局单例
llm_service = LLMService()


# ═══════════════════════════════════════════════════════════════
# AIService — 集中式 AI 管理 (凭据 / 缓存 / 用量 / 限频 / 调用)
# ═══════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_key(prefix: str, content: str) -> str:
    return f"{prefix}:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


class AIService:
    """集中式 AI 服务：凭据 / 缓存 / 用量 / 限频 / 调用统一管理。

    v0.6 P0-⑥ 双引擎收敛：provider 定义（base_url / 模型 / api_key_env）
    与 LLMService 共用 ``config/llm.yaml`` 单一来源（经 ``llm_service.config``）。
    ``FALLBACK_*`` 常量仅在配置缺失/未声明该 provider 时兜底，取值与
    收敛前的硬编码一致，保证无配置环境行为不变。
    """

    # 采集热路径限频：默认 60s 内最多 6 次（商汤免费 rpm 有限）。
    GATE_RATE_WINDOW_S = 60
    GATE_RATE_MAX = 6

    # 无 llm.yaml 或 provider 未声明时的历史兜底值
    FALLBACK_BASE_URLS = {
        "sensenova": "https://token.sensenova.cn/v1",
        "ollama": "http://127.0.0.1:11434",
    }
    FALLBACK_EVAL_MODELS = {
        "sensenova": "sensenova-6.8-flash-lite",
        "ollama": "qwen2.5:7b",
    }

    def __init__(self) -> None:
        self._gate_calls: deque[float] = deque(maxlen=128)

    # ------------------------------------------------------------------
    # provider / 凭据（llm.yaml 单一来源 + env 覆盖）
    # ------------------------------------------------------------------
    @staticmethod
    def _provider_cfg(name: str):
        """取共享 LLMConfig 中 provider 定义；无配置或未声明时返回 None。"""
        cfg = llm_service.config
        if cfg is None:
            return None
        return cfg.providers.get(name)

    @classmethod
    def _base_url(cls, provider: str) -> str:
        """chat 端点 base（不含路径后缀；openai 系拼 /chat/completions）。"""
        pcfg = cls._provider_cfg(provider)
        if pcfg is not None and pcfg.base_url:
            return pcfg.base_url.rstrip("/")
        return cls.FALLBACK_BASE_URLS.get(
            provider, cls.FALLBACK_BASE_URLS["sensenova"])

    @classmethod
    def _eval_model(cls, provider: str) -> str:
        """evaluate / gate_detect 所用模型。"""
        pcfg = cls._provider_cfg(provider)
        if pcfg is not None:
            return pcfg.models.score
        return cls.FALLBACK_EVAL_MODELS.get(
            provider, cls.FALLBACK_EVAL_MODELS["sensenova"])

    @staticmethod
    def _resolve_provider() -> str:
        """默认取 llm.yaml default_provider；AI_PROVIDER 环境变量显式覆盖。"""
        import os
        env = os.environ.get("AI_PROVIDER")
        if env:
            return env
        cfg = llm_service.config
        return cfg.default_provider if cfg is not None else "sensenova"

    @staticmethod
    def _resolve_api_key() -> str:
        """按当前 provider 的 api_key_env 读密钥（不持久化到 settings）。"""
        import os
        p = AIService._resolve_provider()
        pcfg = AIService._provider_cfg(p)
        env_name = (pcfg.api_key_env if pcfg is not None else None) \
            or "SENSENOVA_API_KEY"
        return os.environ.get(env_name, "") or ""

    @staticmethod
    def _ollama_up(timeout: float = 1.0) -> bool:
        import urllib.request
        base = AIService._base_url("ollama")
        try:
            with urllib.request.urlopen(
                f"{base}/api/tags", timeout=timeout
            ):
                return True
        except Exception:
            return False

    def available(self, provider: str | None = None) -> bool:
        """provider 是否就绪。"""
        p = provider or self._resolve_provider()
        if p == "ollama":
            return self._ollama_up()
        return bool(self._resolve_api_key())

    # ------------------------------------------------------------------
    # 限频（供采集热路径门禁用）
    # ------------------------------------------------------------------
    def gate_rate_allowed(self) -> bool:
        now = time.monotonic()
        while self._gate_calls and \
                now - self._gate_calls[0] > self.GATE_RATE_WINDOW_S:
            self._gate_calls.popleft()
        return len(self._gate_calls) < self.GATE_RATE_MAX

    def gate_rate_mark(self) -> None:
        self._gate_calls.append(time.monotonic())

    # ------------------------------------------------------------------
    # 能力：提炼关键内容 + 质量评分（用户保留的唯一 LLM 功能）
    # ------------------------------------------------------------------
    def evaluate(
        self,
        content: str,
        *,
        title: str = "",
        provider: str | None = None,
        api_key: str | None = None,
        timeout: float = 20.0,
    ) -> dict:
        """用大模型评价文章质量并提炼关键内容。

        返回 { ok, provider, quality_score(0-10), verdict, key_points, summary }。
        失败时 ok=False + error（不静默降级，便于人工复核/测试）。
        """
        p = provider or self._resolve_provider()
        key = api_key if api_key is not None else self._resolve_api_key()

        # 缓存
        cache_key = _cache_key("eval", f"{title}|{content}")
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            if p == "ollama":
                result = self._call_ollama_eval(title, content, timeout)
            else:
                result = self._call_sensenova_eval(
                    title, content, key, timeout
                )
        except Exception as e:
            self._usage("evaluate", p, 0, 0.0)
            _logger.warning("ai evaluate failed (%s): %s", p, e)
            return {"ok": False, "provider": p, "error": f"{type(e).__name__}: {str(e)[:300]}"}

        result["ok"] = True
        result["provider"] = result.get("provider", p)
        self._cache_set(cache_key, result)
        self._usage("evaluate", p, _est_tokens(f"{title}{content}"), 0.0)
        return result

    def gate_detect(
        self, title: str, summary: str,
        provider: str | None = None, api_key: str | None = None,
        timeout: float = 8.0,
    ) -> float | None:
        """门禁专用 AI 概率（0..1），带限频；超限/失败返回 None（fail-open）。"""
        p = provider or self._resolve_provider()
        if not self.available(p):
            return None
        # 商汤付费：限频；ollama 本地免费不限。
        if p != "ollama" and not self.gate_rate_allowed():
            return None
        key = api_key if api_key is not None else self._resolve_api_key()
        try:
            if p == "ollama":
                self.gate_rate_mark()
                return self._call_ollama_detect(title, summary, timeout)
            self.gate_rate_mark()
            return self._call_sensenova_detect(title, summary, key, timeout)
        except Exception as e:
            _logger.warning("ai gate-detect failed (%s): %s", p, e)
            return None

    # ------------------------------------------------------------------
    # 缓存 / 用量
    # ------------------------------------------------------------------
    def _cache_get(self, key: str) -> dict | None:
        try:
            conn = get_connection()
            row = conn.execute(
                "SELECT response FROM llm_cache WHERE cache_key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            return json.loads(row["response"])
        except Exception:
            return None

    def _cache_set(self, key: str, value: dict) -> None:
        try:
            conn = get_connection()
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache "
                "(cache_key, provider, model, response, cached_at, ttl_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (key, value.get("provider", ""),
                 self._eval_model(value.get("provider") or "sensenova"),
                 json.dumps(value, ensure_ascii=False), _now_iso(), 86400),
            )
        except Exception:
            pass

    def _usage(self, task: str, provider: str, tokens: int, cost: float) -> None:
        try:
            conn = get_connection()
            conn.execute(
                "INSERT INTO llm_usage_log "
                "(provider, model, task, tokens, cost_usd, latency_ms, occurred_at) "
                "VALUES (?, ?, ?, ?, ?, 0, ?)",
                (provider, self._eval_model(provider), task, tokens, cost,
                 _now_iso()),
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 商汤日日新 / ollama 调用
    # ------------------------------------------------------------------
    def _call_sensenova_eval(self, title: str, content: str, key: str, timeout: float) -> dict:
        prompt = _eval_prompt(title, content)
        url = self._base_url("sensenova") + "/chat/completions"
        payload = {
            "model": self._eval_model("sensenova"),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False, "temperature": 0.2, "max_tokens": 600,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        raw = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return _parse_eval_json(raw, provider="sensenova")

    def _call_ollama_eval(self, title: str, content: str, timeout: float) -> dict:
        prompt = _eval_prompt(title, content)
        url = self._base_url("ollama") + "/api/chat"
        payload = {
            "model": self._eval_model("ollama"),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False, "temperature": 0.2, "options": {"num_predict": 600},
        }
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw = (data.get("message") or {}).get("content", "") or ""
        return _parse_eval_json(raw, provider="ollama")

    def _call_sensenova_detect(self, title: str, summary: str, key: str, timeout: float) -> float:
        text = f"标题：{title}\n摘要：{summary}"
        url = self._base_url("sensenova") + "/chat/completions"
        payload = {
            "model": self._eval_model("sensenova"),
            "messages": [
                {"role": "system", "content": _DETECT_SYSTEM},
                {"role": "user", "content": text},
            ],
            "stream": False, "temperature": 0.0, "max_tokens": 8,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        raw = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return _parse_score01(raw)

    def _call_ollama_detect(self, title: str, summary: str, timeout: float) -> float:
        text = f"标题：{title}\n摘要：{summary}"
        url = self._base_url("ollama") + "/api/chat"
        payload = {
            "model": self._eval_model("ollama"),
            "messages": [
                {"role": "system", "content": _DETECT_SYSTEM},
                {"role": "user", "content": text},
            ],
            "stream": False, "temperature": 0.0, "options": {"num_predict": 8},
        }
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw = (data.get("message") or {}).get("content", "") or ""
        return _parse_score01(raw)


# 全局单例
ai_service = AIService()


# ═══════════════════════════════════════════════════════════════
# Prompt / 解析 (AI 能力辅助)
# ═══════════════════════════════════════════════════════════════
_DETECT_SYSTEM = (
    "你是一名内容质量审查员。判断下面的资讯是否为AI批量生成的低信息密度内容"
    "或营销软文。只输出一个0到1的数字（1=极可能AI生成/软文，0=真实高信息密度），"
    "不要输出任何其他文字。"
)


def _eval_prompt(title: str, content: str) -> str:
    title_line = f"标题：{title}\n" if title else ""
    return (
        "你是一名资深内容质量评审。请对下面的文章做两件事，并严格以 JSON 输出"
        "（不要任何其他文字）：\n"
        "1. 评价文章质量，fields: {\"score\": 0到10的浮点数，"
        "\"verdict\": 一句话总体评价}\n"
        "2. 提取文章关键内容，fields: {\"summary\": 2-3句摘要, "
        "\"key_points\": [3-6个要点字符串]}\n"
        f"输出格式：{{\"score\": <0-10>,\"verdict\":\"...\","
        f"\"summary\":\"...\",\"key_points\":[\"...\",\"...\"]}}\n\n"
        f"{title_line}文章内容：\n{content[:4000]}"
    )


def _parse_eval_json(raw: str, *, provider: str) -> dict:
    import re
    try:
        start, end = raw.index("{"), raw.rindex("}")
        data = json.loads(raw[start:end + 1])
        if isinstance(data, dict):
            return {
                "provider": provider,
                "quality_score": float(data.get("score", DEFAULT_SCORE)),
                "verdict": str(data.get("verdict", "")),
                "summary": str(data.get("summary", "")),
                "key_points": [str(k) for k in data.get("key_points", [])],
            }
    except (ValueError, json.JSONDecodeError):
        pass
    m = re.search(r"\"score\"\s*:\s*(\d+(?:\.\d+)?)", raw)
    score = float(m.group(1)) if m else DEFAULT_SCORE
    return {
        "provider": provider,
        "quality_score": score,
        "verdict": raw[:200],
        "summary": "",
        "key_points": [],
    }


def _parse_score01(raw: str) -> float:
    import re
    m = re.search(r"(?:0(?:\.\d+)?|1(?:\.0+)?)", (raw or "").strip())
    if not m:
        return 0.0
    return max(0.0, min(1.0, float(m.group(0))))


def _est_tokens(text: str) -> int:
    return len(text) // 4


# ═══════════════════════════════════════════════════════════════
# evaluate_article — 文章评价统一入口 (M5 合并后单契约)
# ═══════════════════════════════════════════════════════════════
async def evaluate_article(
    content: str,
    *,
    title: str = "",
    provider: str | None = None,
    api_key: str | None = None,
    timeout: float = 20.0,
) -> dict:
    """用大模型评价文章质量并提炼关键内容（统一委托 AIService）。

    凭据 / 缓存 / 用量 / 限频统一由 ``ai_service`` 管理（env 优先，
    不再读 settings 表）。返回结构化结果：

        { ok, provider, quality_score(0-10), verdict,
          key_points: [str], summary, error? }

    失败时 ok=False + error（不静默降级，便于测试定位）。
    """
    import asyncio

    def _call():
        return ai_service.evaluate(
            content, title=title, provider=provider,
            api_key=api_key, timeout=timeout,
        )

    # evaluate 为同步阻塞的 httpx 调用，放入线程池避免阻塞事件循环
    return await asyncio.to_thread(_call)


# ═══════════════════════════════════════════════════════════════
# ai_scores 写路径唯一入口 (SPEC §1 Task19)
# ═══════════════════════════════════════════════════════════════
def write_score(
    hotspot_id: str,
    score: float,
    *,
    reason: str = "ai_hub",
    scorer: str | None = None,
) -> int | None:
    """写入 ``ai_scores`` 表 — 生产代码唯一 INSERT 入口。

    SPEC §1 Task19: ``ai_scores`` 写路径仅本函数命中; mcp_agent_tools 的
    ``score_item`` 与 T1 的 LLM 评分审计都必须经此调用。

    Args:
        hotspot_id: 关联 hotspot / knowledge item id
        score: 0-10 评分
        reason: 评分理由/来源 (如 llm_service / agent:claude-desktop)
        scorer: 评分者标识 (MCP agent 工具用), 默认 None

    Returns:
        lastrowid; 失败返回 None (评分是审计增强, 静默降级不阻塞业务)。
    """
    try:
        cur = get_connection().execute(
            "INSERT INTO ai_scores (hotspot_id, score, reason, scorer, scored_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (hotspot_id, float(score), reason, scorer, _now_iso()),
        )
        return cur.lastrowid
    except Exception as e:
        log.warning(f"write_score failed for {hotspot_id}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# 知识写回唯一门面 (v0.5 §18.2 强约束 1)
# ═══════════════════════════════════════════════════════════════
def write_item(
    item: dict,
    content: str | None = None,
    *,
    kind: str = "agent_write",
    agent: str = "",
) -> None:
    """写回 ``knowledge/items/{id}.md`` 并在 wiki_events 留痕。

    md 写失败向上抛错 (真相源必须成功); 遥测失败静默降级 (不阻塞写路径)。

    Args:
        item: knowledge_items dict (须含 id)
        content: Markdown 正文 (None=保留文件已有正文, ''=清空)
        kind: wiki_events 事件类型, 默认 agent_write
        agent: 产生者标识, 如 api:patch_item / mcp:wiki_write
    """
    from backend.services import knowledge_sync

    knowledge_sync.write_item_to_md(item, content=content)
    item_id = str(item.get("id", ""))
    try:
        from backend.repository.wiki_event_repo import wiki_event_repo

        wiki_event_repo.log(
            kind=kind,
            wiki_path=f"items/{item_id}.md",
            db_table="knowledge_items",
            db_row_id=item_id,
            agent=agent,
        )
    except Exception as e:
        log.debug(f"wiki_events log skipped for items/{item_id}.md: {e}")


def update_frontmatter(
    rel_path: str,
    key: str,
    value: str,
    *,
    kind: str = "agent_write",
    agent: str = "",
) -> bool:
    """就地更新 md frontmatter 单字段并留痕。

    Args:
        rel_path: 相对 knowledge/ 的路径, 如 ``concepts/zero-trust.md``
        key/value: 要写入的 frontmatter 字段
        kind/agent: wiki_events 事件类型与产生者

    Returns True on success (同 knowledge_sync.update_md_frontmatter_field)。
    """
    from backend.services.knowledge_sync import KNOWLEDGE_DIR, update_md_frontmatter_field

    ok = update_md_frontmatter_field(KNOWLEDGE_DIR / rel_path, key, value)
    if ok:
        try:
            from backend.repository.wiki_event_repo import wiki_event_repo

            wiki_event_repo.log(kind=kind, wiki_path=rel_path, agent=agent)
        except Exception as e:
            log.debug(f"wiki_events log skipped for {rel_path}: {e}")
    return ok


__all__ = [
    "COST_PER_1M_TOKENS",
    "DEFAULT_SCORE",
    "AIService",
    "LLMService",
    "ai_service",
    "evaluate_article",
    "llm_service",
    "update_frontmatter",
    "write_item",
    "write_score",
]

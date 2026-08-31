"""ai_hub/service.py — AIService 集中式 AI 编排 (v0.7 Step 2 拆分自 tasks.py)。

原 ``backend/services/ai_hub/tasks.py`` (412 行) 拆为:
- ``service.py`` (本文件, ~290 行) — ``AIService`` 整个类 (评价/门禁/限频/缓存/用量)
- ``tasks.py`` (剩余 ~80 行) — 评价辅助 (_eval_prompt / _parse_* / _est_tokens) + ``evaluate_article`` 入口

向后兼容: ``from backend.services.ai_hub import AIService, ai_service`` 仍可解析
(由 ``__init__.py`` re-export 统一暴露).
"""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import ClassVar

import httpx

from backend.logging_config import logger as _logger
from backend.services.ai_hub.cache import get_ai_cache, set_ai_cache
from backend.services.ai_hub.gateway import llm_service

log = logging.getLogger("hotspot.ai_hub")


# Prompt 常量 — AIService._call_sensenova_detect / _call_ollama_detect 使用
_DETECT_SYSTEM = (
    "你是一名内容质量审查员。判断下面的资讯是否为AI批量生成的低信息密度内容"
    "或营销软文。只输出一个0到1的数字（1=极可能AI生成/软文，0=真实高信息密度），"
    "不要输出任何其他文字。"
)


class AIService:
    """集中式 AI 服务：凭据 / 缓存 / 限频 / 调用统一管理。

    v0.6 P0-⑥ 双引擎收敛：provider 定义（base_url / 模型 / api_key_env）
    与 LLMService 共用 ``config/llm.yaml`` 单一来源（经 ``llm_service.config``）。
    ``FALLBACK_*`` 常量仅在配置缺失/未声明该 provider 时兜底，取值与
    收敛前的硬编码一致，保证无配置环境行为不变。
    """

    # 采集热路径限频：默认 60s 内最多 6 次（商汤免费 rpm 有限）。
    GATE_RATE_WINDOW_S = 60
    GATE_RATE_MAX = 6

    # 无 llm.yaml 或 provider 未声明时的历史兜底值
    FALLBACK_BASE_URLS: ClassVar[dict[str, str]] = {
        "sensenova": "https://token.sensenova.cn/v1",
        "ollama": "http://127.0.0.1:11434",
    }
    FALLBACK_EVAL_MODELS: ClassVar[dict[str, str]] = {
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
        """v0.7 Batch 2: 四级优先级 — env > settings.kv > router > default。

        三级链 (env/router/default) 是 ``test_s4_1_model_router`` 既有断言的
        硬约束。Batch 2 把 settings.kv 插在 env 之后、router 之前 — 当前端
        切换过 ``llm.default_provider`` 时覆盖 env, 当未切换时退回 env。
        这符合 PRD §5.3 "用户切换 > 运维默认"。

        不读 ``quality.llm_provider``: 那是 QualityRules 死字段 (v4.4 起
        ai_hub 不接), 仍由 ``PUT /api/quality/rules`` 维护。
        """
        import os
        env = os.environ.get("AI_PROVIDER")
        if env:
            return env

        # v0.7 Batch 2: settings.kv "llm.default_provider" 覆盖 (env 之后)
        try:
            from backend.repository.settings_repo import SettingsRepository
            kv_provider = SettingsRepository().get("llm.default_provider")
            if isinstance(kv_provider, str) and kv_provider.strip():
                return kv_provider.strip()
        except Exception as e:
            log.debug(f"_resolve_provider settings.kv fallback: {e}")

        try:
            from backend.services.llm.model_router import route_model
            # AIService 的 evaluate/gate_detect 是标准分析档; router 推荐最稳的 provider
            routed = route_model("evaluate", config=llm_service.config)
            if routed and routed[0]:
                return routed[0]
        except Exception as e:
            log.debug(f"AIService._resolve_provider router fallback: {e}")
        cfg = llm_service.config
        return cfg.default_provider if cfg is not None else "sensenova"

    @staticmethod
    def _config_source() -> str:
        """v0.7 Batch 2: 解析路径打标 (env|settings|router|default)。

        与 :meth:`_resolve_provider` 走同一路径, 但返回来源而非 provider 名;
        调用方写入 ``record_llm_call(config_source=...)``, 看板可按来源
        聚合 (例: 用户切换过几次 / 当前生效比例)。

        不抛 — 任一层失败回退到下一层, 与 ``_resolve_provider`` 等价。
        settings.kv 的非字符串值 (typo 写入 list/dict) **不算** settings 命中,
        因为 resolver 不会接受它, 故打标与解析保持一致。
        """
        import os
        if os.environ.get("AI_PROVIDER"):
            return "env"
        try:
            from backend.repository.settings_repo import SettingsRepository
            kv_provider = SettingsRepository().get("llm.default_provider")
            if isinstance(kv_provider, str) and kv_provider.strip():
                return "settings"
        except Exception:
            pass
        try:
            from backend.services.llm.model_router import route_model
            if route_model("evaluate", config=llm_service.config):
                return "router"
        except Exception:
            pass
        return "default"

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

        # 缓存 (复用 tasks._cache_key 避免重复定义)
        from backend.services.ai_hub.tasks import _cache_key, _est_tokens
        cache_key = _cache_key("eval", f"{title}|{content}")
        if self._cache_get(cache_key) is not None:
            return self._cache_get(cache_key)

        try:
            t0 = time.monotonic()
            if p == "ollama":
                result = self._call_ollama_eval(title, content, timeout)
            else:
                result = self._call_sensenova_eval(
                    title, content, key, timeout
                )
        except Exception as e:
            self._record(p, self._eval_model(p), "evaluate",
                         ok=False, error=f"{type(e).__name__}: {e}",
                         latency_ms=(time.monotonic() - t0) * 1000,
                         scene="evaluate_article",
                         config_source=self._config_source(),
                         key_source="env")
            _logger.warning("ai evaluate failed ({}): {}: {}", p, type(e).__name__, e)
            return {"ok": False, "provider": p, "error": f"{type(e).__name__}: {str(e)[:300]}"}

        result["ok"] = True
        result["provider"] = result.get("provider", p)
        self._cache_set(cache_key, result)
        self._record(p, self._eval_model(p), "evaluate",
                     ok=True,
                     prompt=f"{title}\n{content}",
                     response=result.get("summary", ""),
                     total_tokens=_est_tokens(f"{title}{content}"),
                     latency_ms=(time.monotonic() - t0) * 1000,
                     scene="evaluate_article",
                     config_source=self._config_source(),
                     key_source="env")
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
            _logger.warning("ai gate-detect failed ({}): {}: {}", p, type(e).__name__, e)
            return None

    # ------------------------------------------------------------------
    # 商汤日日新 / ollama 调用
    # ------------------------------------------------------------------
    def _call_sensenova_eval(self, title: str, content: str, key: str, timeout: float) -> dict:
        from backend.services.ai_hub.tasks import _eval_prompt, _parse_eval_json
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
        from backend.services.ai_hub.tasks import _eval_prompt, _parse_eval_json
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
        from backend.services.ai_hub.tasks import _parse_score01
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
        from backend.services.ai_hub.tasks import _parse_score01
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

    # ------------------------------------------------------------------
    # 向后兼容：旧版 _cache_get/_cache_set 方法签名
    # (测试 monkeypatch 仍通过 ai_service 实例调用)
    # ------------------------------------------------------------------
    def _cache_get(self, key: str) -> dict | None:
        return get_ai_cache(key)

    def _cache_set(self, key: str, value: dict) -> None:
        set_ai_cache(key, value)

    def _usage(
        self, provider: str, model: str, task: str, tokens: int, cost: float,
    ) -> None:
        """[deprecated v0.7 Batch 1] 旧接口, 保留签名兼容旧测试桩 (lambda *a)。

        推荐改用 :meth:`_record` (新统一入口)。本方法内部直接转发到
        record_llm_call 保证旧链路不破。
        """
        from .usage import record_llm_call
        record_llm_call(
            provider=provider, model=model, task=task,
            total_tokens=int(tokens), cost_usd=float(cost),
            ok=True, scene="legacy_ai_usage",
        )

    def _record(
        self,
        provider: str,
        model: str,
        task: str,
        *,
        ok: bool,
        error: str | None = None,
        prompt: str | None = None,
        response: str | None = None,
        total_tokens: int | None = None,
        cost_usd: float | None = None,
        latency_ms: float = 0.0,
        scene: str | None = None,
        config_source: str | None = None,
        key_source: str | None = None,
    ) -> None:
        """v0.7 Batch 1: AIService 内部 record_llm_call 薄包装 (避免每个调用
        点重复 import)。参数语义与 usage.record_llm_call 一致 (见该处文档)。
        """
        from .usage import record_llm_call
        record_llm_call(
            provider=provider, model=model, task=task,
            ok=ok, error=error, prompt=prompt, response=response,
            total_tokens=total_tokens, cost_usd=cost_usd,
            latency_ms=latency_ms, scene=scene,
            config_source=config_source, key_source=key_source,
        )

    def _default_provider(self) -> str:
        """当前解析后的 default provider 名 (用于 config_source 判定)。

        返回值供 :meth:`_record` 调用方作为 "default" 源判定基准。
        AIService 不持 LLMConfig, 借 gateway.llm_service.config 间接读。
        """
        try:
            cfg = llm_service.config
            return cfg.default_provider if cfg else "sensenova"
        except Exception:
            return "sensenova"


# 全局单例
ai_service = AIService()


# Re-export 提示常量供 tasks.py 复用
__all__ = ["_DETECT_SYSTEM", "AIService", "ai_service"]

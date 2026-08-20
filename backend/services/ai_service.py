"""AIService — 集中式 AI 管理层 (v4.4 重构).

第一性原理
----------
此前 LLM 凭据 / 缓存 / 用量 / 限频散布在 ai_quality_gate、llm_service、
T1/T3 触发器中，导致：
- 采集热路径逐条调 LLM → 打爆商汤配额 (429)；
- 凭据多路（settings 表 + 环境变量 + llm.yaml）语义分裂；
- 无统一限频与调用记录。

本次重构把「所有 AI 能力」集中到单一服务：
- 凭据：env（SENSENOVA_API_KEY / 本地 ollama）统一解析，不再持久化到
  settings 表（移除设置页密钥保存配置）。
- 缓存：统一写入 ``llm_cache``。
- 用量：统一写入 ``llm_usage_log``（task 细分）。
- 限频：进程级时间窗节流，供采集热路径（门禁）使用。
- 能力：``evaluate()`` 评分+提炼关键内容，``gate_detect()`` 门禁 AI 概率。

管线上游（T1 ai_scores / T3 摘要 / evaluate 端点）全部走本服务，
保证「所有调用 AI 的能力集中管理」。
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from datetime import datetime, timezone

import httpx

from backend.logging_config import logger as _logger

# 默认评分兜底
DEFAULT_SCORE = 5.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_key(prefix: str, content: str) -> str:
    return f"{prefix}:{hashlib.sha256(content.encode()).hexdigest()[:16]}"


class AIService:
    """集中式 AI 服务：凭据 / 缓存 / 用量 / 限频 / 调用统一管理。"""

    # 采集热路径限频：默认 60s 内最多 6 次（商汤免费 rpm 有限）。
    GATE_RATE_WINDOW_S = 60
    GATE_RATE_MAX = 6

    def __init__(self) -> None:
        self._gate_calls: deque[float] = deque(maxlen=128)

    # ------------------------------------------------------------------
    # provider / 凭据
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_provider() -> str:
        """默认 sensenova，环境变量显式指定时可用 ollama。"""
        import os
        return os.environ.get("AI_PROVIDER", "sensenova")

    @staticmethod
    def _resolve_api_key() -> str:
        """从环境变量读商汤 key（不再持久化到 settings）。"""
        import os
        return os.environ.get("SENSENOVA_API_KEY", "") or ""

    @staticmethod
    def _ollama_up(timeout: float = 1.0) -> bool:
        import urllib.request
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:11434/api/tags", timeout=timeout
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
            from backend.repository.db import get_connection
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
            from backend.repository.db import get_connection
            conn = get_connection()
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache "
                "(cache_key, provider, model, response, cached_at, ttl_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (key, value.get("provider", ""), "sensenova-6.8-flash-lite",
                 json.dumps(value, ensure_ascii=False), _now_iso(), 86400),
            )
        except Exception:
            pass

    def _usage(self, task: str, provider: str, tokens: int, cost: float) -> None:
        try:
            from backend.repository.db import get_connection
            conn = get_connection()
            conn.execute(
                "INSERT INTO llm_usage_log "
                "(provider, model, task, tokens, cost_usd, latency_ms, occurred_at) "
                "VALUES (?, ?, ?, ?, ?, 0, ?)",
                (provider, "sensenova-6.8-flash-lite", task, tokens, cost, _now_iso()),
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 商汤日日新 / ollama 调用
    # ------------------------------------------------------------------
    def _call_sensenova_eval(self, title: str, content: str, key: str, timeout: float) -> dict:
        prompt = _eval_prompt(title, content)
        url = "https://token.sensenova.cn/v1/chat/completions"
        payload = {
            "model": "sensenova-6.8-flash-lite",
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
        url = "http://127.0.0.1:11434/api/chat"
        payload = {
            "model": "qwen2.5:7b",
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
        url = "https://token.sensenova.cn/v1/chat/completions"
        payload = {
            "model": "sensenova-6.8-flash-lite",
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
        url = "http://127.0.0.1:11434/api/chat"
        payload = {
            "model": "qwen2.5:7b",
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


# ---------------------------------------------------------------------------
# Prompt / 解析
# ---------------------------------------------------------------------------
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


__all__ = ["AIService", "ai_service"]
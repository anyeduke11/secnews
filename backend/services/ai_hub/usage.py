"""ai_hub/usage.py — LLM 用量日志统一操作 (llm_usage_log 表)。

LLMService 与 AIService 共享 ``llm_usage_log`` 表。
本模块提供两套接口，避免两个类耦合。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.repository.db import get_connection

log = logging.getLogger("hotspot.ai_hub")


# ── LLMService 用量 ─────────────────────────────────────────────

def log_llm_usage(
    provider: str,
    model: str,
    task: str,
    prompt: str,
    response: str,
) -> None:
    """记录 LLMService 调用用量。"""
    try:
        prompt_tokens = len(prompt) // 4  # 粗略估算
        response_tokens = len(response) // 4
        total_tokens = prompt_tokens + response_tokens
        # 成本估算
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


# ── AIService 用量 ─────────────────────────────────────────────

def log_ai_usage(
    provider: str,
    model: str,
    task: str,
    tokens: int,
    cost: float,
) -> None:
    """记录 AIService 调用用量。"""
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO llm_usage_log "
            "(provider, model, task, tokens, cost_usd, latency_ms, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?)",
            (provider, model, task, tokens, cost,
             datetime.now(timezone.utc).isoformat()),
        )
    except Exception:
        pass


# ── 内部辅助 ─────────────────────────────────────────────────────

def _estimate_cost(model: str, tokens: int) -> float:
    """估算一次 LLM 调用的 USD 成本."""
    if tokens <= 0:
        return 0.0

    COST_PER_1M_TOKENS: dict[str, float] = {
        "gpt-4o-mini": 0.15,
        "gpt-4o": 5.0,
        "qwen-turbo": 0.3,
        "qwen-plus": 0.8,
        "claude-3-5-haiku-20241022": 0.8,
        "claude-3-5-sonnet-20241022": 3.0,
    }
    rate = COST_PER_1M_TOKENS.get(model, 0.5)
    return (tokens / 1_000_000) * rate

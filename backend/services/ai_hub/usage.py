"""ai_hub/usage.py — LLM 用量日志统一操作 (llm_usage_log 表)。

LLMService 与 AIService 共享 ``llm_usage_log`` 表。
本模块提供两套接口，避免两个类耦合。

v0.6.3 P3-3 观测面: llm_usage_log 只记**成功**调用, 失败此前只进
logger.warning 后即消失 —— "AI 是否真在工作" 无法判读 (审计架构弱点 ④)。
新增进程内错误环 ``record_llm_error`` / ``recent_llm_errors()``, 与
``recent_calls()`` 一起由 /api/llm/status 汇聚输出。
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone

from backend.repository.db import get_connection

log = logging.getLogger("hotspot.ai_hub")

# 进程内错误环 (失败不落库: llm_usage_log 无 ok/error 列, 加列需迁移,
# 进程内环足够回答"最近是否有失败/最后错误是什么")
_ERROR_RING: deque[dict] = deque(maxlen=50)


def record_llm_error(task: str, provider: str, error: str) -> None:
    """记录一次 LLM 调用失败 (gateway 各 provider except 处调用)。"""
    _ERROR_RING.append(
        {
            "task": task,
            "provider": provider,
            "error": str(error)[:300],
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def recent_llm_errors() -> list[dict]:
    """最近的 LLM 调用失败 (进程生命周期内, 最多 50 条)。"""
    return list(_ERROR_RING)


def recent_calls(limit: int = 20) -> list[dict]:
    """最近 N 次成功调用 (llm_usage_log, 倒序)。"""
    try:
        rows = get_connection().execute(
            "SELECT provider, model, task, tokens, cost_usd, occurred_at "
            "FROM llm_usage_log ORDER BY occurred_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def success_stats_24h() -> dict:
    """24h 窗口成功调用统计 + 进程内错误数 (成功率分母仅含进程内错误)。"""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    try:
        row = get_connection().execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(tokens), 0) AS tokens "
            "FROM llm_usage_log WHERE occurred_at >= ?",
            (cutoff,),
        ).fetchone()
        ok_24h, tokens_24h = int(row["n"]), int(row["tokens"])
    except Exception:
        ok_24h, tokens_24h = 0, 0
    errors = len(_ERROR_RING)
    total = ok_24h + errors
    return {
        "ok_calls_24h": ok_24h,
        "tokens_24h": tokens_24h,
        "errors_in_process": errors,
        # 诚实口径: 错误环随进程重启清零, 成功率是"本进程窗口"而非全天
        "success_rate": round(ok_24h / total, 3) if total else None,
    }


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

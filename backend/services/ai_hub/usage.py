"""ai_hub/usage.py — LLM 用量日志统一操作 (v0.7 Observability Batch 1)。

LLMService 与 AIService 共享 ``llm_usage_log`` 表。
本模块提供两套接口，避免两个类耦合。

历史 (v0.6.3 P3-3): llm_usage_log 只记**成功**调用, 失败此前只进
logger.warning 后即消失 —— "AI 是否真在工作" 无法判读 (审计架构弱点 ④)。
新增进程内错误环 ``record_llm_error`` / ``recent_llm_errors()``, 与
``recent_calls()`` 一起由 /api/llm/status 汇聚输出。

v0.7 Batch 1 变更 (docs/Observability_PRD_v1.0.md §5.2):
1. ``record_llm_call()`` 统一单入口, 替换散落的 log_llm_usage / log_ai_usage
   / cost_monitor.record_usage。成功失败都落表, 真实 latency/真值 tokens、
   trace_id (从 contextvar 取) / scene / config_source / key_source 全带上。
2. cost_monitor.record_usage 改为调 record_llm_call (避免双 INSERT 漂移)。
3. log_llm_usage / log_ai_usage 标记为 deprecated 但保留 (向后兼容 / 测试桩)。
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone

from backend.observability import get_trace_id
from backend.repository.db import get_connection

log = logging.getLogger("hotspot.ai_hub")

# 进程内错误环 (失败不落库的历史契约已废除: 现在 record_llm_call 失败路径
# 也会写 llm_usage_log ok=0; 错误环仅作热路径告警源 / /api/llm/status
# 实时近期错误展示。重启清零符合 "本进程窗口" 口径。)
_ERROR_RING: deque[dict] = deque(maxlen=50)


def record_llm_error(task: str, provider: str, error: str) -> None:
    """记录一次 LLM 调用失败 (gateway 各 provider except 处调用)。

    v0.7 Batch 1 仍保留: 用于 /api/llm/status 的最近错误展示 (热路径) 与
    实时告警评估。持久化路径走 record_llm_call。
    """
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
    """最近 N 次成功调用 (llm_usage_log, 倒序)。

    v0.7 Batch 1: 同时返回 ok 字段, 调用方 /api/llm/status 可区分。
    """
    try:
        rows = get_connection().execute(
            "SELECT provider, model, task, tokens, cost_usd, latency_ms, "
            "ok, scene, trace_id, occurred_at "
            "FROM llm_usage_log ORDER BY occurred_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def success_stats_24h() -> dict:
    """24h 窗口统计 (ok_calls_24h / tokens_24h / 成功率 / latency p50)。

    v0.7 Batch 1: 成功率分母 = llm_usage_log 真实窗口 (24h 持久化),
    不再依赖进程内错误环 (那是热路径展示用)。

    v0.7 Batch 1 PRD §5.2 ①: 补 latency p50 (成功调用) — SQLite 无
    MEDIAN, 用 ROW_NUMBER() over 窗 + 中位行 trick; 失败路径延迟分布
    与成功显著不同, 不计入 p50。
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    try:
        rows = get_connection().execute(
            "SELECT ok, COUNT(*) AS n, COALESCE(SUM(tokens), 0) AS tokens "
            "FROM llm_usage_log WHERE occurred_at >= ? GROUP BY ok",
            (cutoff,),
        ).fetchall()
        ok_n = sum(int(r["n"]) for r in rows if int(r["ok"]) == 1)
        fail_n = sum(int(r["n"]) for r in rows if int(r["ok"]) == 0)
        tokens_24h = sum(int(r["tokens"]) for r in rows)
        total = ok_n + fail_n
        # 进程内错误数仍暴露 (热路径告警), 但不计入 24h 成功率分母
        errors_in_process = len(_ERROR_RING)
        # latency p50 — 只算 ok=1 的成功路径
        p50_row = get_connection().execute(
            "SELECT latency_ms FROM ("
            "  SELECT latency_ms, ROW_NUMBER() OVER "
            "    (ORDER BY latency_ms) AS rn, "
            "    COUNT(*) OVER () AS cnt "
            "  FROM llm_usage_log "
            "  WHERE occurred_at >= ? AND ok = 1 AND latency_ms IS NOT NULL"
            ") WHERE rn = CAST((cnt + 1) AS INTEGER) / 2 LIMIT 1",
            (cutoff,),
        ).fetchone()
        latency_p50_ms = round(float(p50_row["latency_ms"]), 1) if p50_row else None
        return {
            "ok_calls_24h": ok_n,
            "fail_calls_24h": fail_n,
            "tokens_24h": tokens_24h,
            "errors_in_process": errors_in_process,
            "success_rate": round(ok_n / total, 3) if total else None,
            "latency_p50_ms": latency_p50_ms,
        }
    except Exception:
        return {"ok_calls_24h": 0, "fail_calls_24h": 0, "tokens_24h": 0,
                "errors_in_process": len(_ERROR_RING), "success_rate": None,
                "latency_p50_ms": None}


# ── 统一记录入口 (v0.7 Batch 1) ────────────────────────────────


def record_llm_call(
    *,
    provider: str,
    model: str,
    task: str,
    prompt: str | None = None,
    response: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_usd: float | None = None,
    latency_ms: float = 0.0,
    ok: bool = True,
    error: str | None = None,
    scene: str | None = None,
    config_source: str | None = None,
    key_source: str | None = None,
    trace_id: str | None = None,
) -> None:
    """单入口记录 LLM 调用 (成功+失败都写 llm_usage_log)。

    Args:
        provider/model/task: 必填, 索引键。
        prompt/response: 全文 (用于估算; 已有真值 tokens 时可传 None)。
        prompt_tokens/completion_tokens/total_tokens: 真值 (可取响应 usage 时);
            留 None 时按 len//4 估算 total_tokens 并标 tokens_estimated=1。
        cost_usd: 已算好的成本; 留 None 时按 _estimate_cost(model, total_tokens) 算。
        latency_ms: 真实耗时 (gateway._call_provider 已用 time.monotonic() 算好)。
        ok: True=成功, False=失败 (此时 error 必填, latency_ms 仍记)。
        error: 失败摘要 (≤300 字, gateway 已有切片)。
        scene: 业务场景 (digest / t1_score / gate_detect / evaluate / config_test /
            agent_builtin), 方便聚合。
        config_source: provider 解析来源 (task_override / router / fallback /
            default / env) —— 写空时表示无法判读。
        key_source: 密钥来源 (secrets / env / none)。
        trace_id: 调用方显式传; 留 None 时从 observability.get_trace_id() 取。

    写入策略:
    - 所有异常 try/except 吞, 永不阻塞主流程 (v0.6.3 P3-3 防御风格延续)。
    - 真值 vs 估算 tokens 通过 tokens_estimated 列区分, 看板可选择性显示。
    """
    try:
        # tokens 真值 vs 估算
        if total_tokens is None:
            if prompt_tokens is not None and completion_tokens is not None:
                total_tokens = int(prompt_tokens) + int(completion_tokens)
                tokens_estimated = 0
            elif prompt is not None and response is not None:
                total_tokens = (len(prompt) + len(response)) // 4
                tokens_estimated = 1
            else:
                total_tokens = 0
                tokens_estimated = 1
        else:
            tokens_estimated = 0

        # cost 真值 vs 估算
        if cost_usd is None:
            from .prompts import _estimate_cost
            cost_usd = _estimate_cost(model or "", int(total_tokens))

        # trace_id 兜底从 contextvar 取 (PRD §5.3)
        if not trace_id:
            trace_id = get_trace_id()

        get_connection().execute(
            "INSERT INTO llm_usage_log "
            "(provider, model, task, tokens, cost_usd, latency_ms, ok, error, "
            " prompt_tokens, completion_tokens, tokens_estimated, "
            " trace_id, scene, config_source, key_source, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                provider, model, task,
                int(total_tokens), float(cost_usd), float(latency_ms),
                1 if ok else 0,
                (str(error)[:300] if error else None),
                int(prompt_tokens) if prompt_tokens is not None else None,
                int(completion_tokens) if completion_tokens is not None else None,
                int(tokens_estimated),
                trace_id, scene, config_source, key_source,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    except Exception as e:
        log.debug(f"record_llm_call failed: {e}")


# ── 兼容旧接口 (deprecated) ──────────────────────────────────


def log_llm_usage(
    provider: str,
    model: str,
    task: str,
    prompt: str,
    response: str,
) -> None:
    """[deprecated v0.7] 旧入口 - 由 record_llm_call 取代, 仅保留给旧测试桩。

    新代码 (gateway/service) 改用 record_llm_call; 旧调用点 log.warning
    提示迁移方向 (一次性, 不刷屏)。仍 INSERT 一行保证旧链路不破。
    """
    log.debug(f"log_llm_usage (deprecated) called for {provider}/{model}/{task}")
    record_llm_call(
        provider=provider, model=model, task=task,
        prompt=prompt, response=response, ok=True, scene="legacy_log_llm_usage",
    )


def log_ai_usage(
    provider: str,
    model: str,
    task: str,
    tokens: int,
    cost: float,
) -> None:
    """[deprecated v0.7] 旧入口 - 由 record_llm_call 取代, 仅保留给旧测试桩。"""
    log.debug(f"log_ai_usage (deprecated) called for {provider}/{model}/{task}")
    record_llm_call(
        provider=provider, model=model, task=task,
        total_tokens=int(tokens), cost_usd=float(cost), ok=True,
        scene="legacy_log_ai_usage",
    )


__all__ = [
    "log_ai_usage",  # deprecated
    "log_llm_usage",  # deprecated
    "recent_calls",
    "recent_llm_errors",
    "record_llm_call",
    "record_llm_error",
    "success_stats_24h",
]

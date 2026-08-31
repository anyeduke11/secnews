"""Phase 5 可观测性 - 统一事件打点 + trace_id 贯穿 (v0.7 Batch 1)。

设计
----
- 单个入口 ``log_event(event, **fields)`` 封装 logger.info
- 所有事件带 ``event=<name>`` 字段便于 grep / 过滤
- trace_id 通过 contextvar 贯穿: 中间件 / instrument_job / agent_bridge
  三处 set, 业务代码任意位置 get_trace_id() 即取到当前请求/job/agent
  关联键。LLM 调用 (record_llm_call) 与 api_events/job_runs/agent_runs
  持久化时都通过 get_trace_id() 写, 实现跨边界串联 (PRD §5.3)
- 不阻塞业务（任何 logger 异常 try/except 吞掉）
- 不在 observability 里改任何业务逻辑，只做日志输出

事件清单
--------
- ``cache_hit``        list/detail/static 命中
- ``cache_miss``       命中失败
- ``cache_invalidate`` 失效若干 key
- ``collect_start``    BaseCollector.fetch 入口
- ``collect_end``      BaseCollector.fetch 出口（含 duration/status）
- ``api_request``      TraceIDMiddleware 入口
- ``api_response``     TraceIDMiddleware 出口（含 status/duration_ms）
- ``startup_complete`` lifespan yield 前（含 startup_duration_ms）
- ``llm_call``         ai_hub.record_llm_call 出口 (含 ok/latency_ms/scene)
"""
from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

from backend.logging_config import logger

# 进程级启动时间（首次访问时记录；可在 main.py lifespan 覆盖）
_START_TIME: float = time.time()

# ── trace_id contextvar (v0.7 Batch 1) ──────────────────────────
# 三源 set:
#   - TraceIDMiddleware.dispatch: HTTP 请求入口 (middleware.py:35)
#   - instrument_job wrapper: scheduler job 入口 (jobs/_runtime.py)
#   - agent_bridge.run_agent_task: agent 入口 (agent_bridge.py)
# 多源 set 互不干扰: HTTP 入口自动 set, job 入口 reset (后端 job 不继承 HTTP trace)。
# token 唯一; 不同任务并发跑, 每个协程有自己独立的 contextvar 值。
_trace_id_var: ContextVar[str | None] = ContextVar("hotspot_trace_id", default=None)


def set_trace_id(trace_id: str):
    """设置当前上下文的 trace_id, 返回 ``ContextVar.Token`` 供 reset 用。

    Args:
        trace_id: 关联键 (UUIDv4 hex / job:<type>:<ts> / agent:<name>:<ts> / None)
    Returns:
        Token (供 ``reset_trace_id(token)`` 恢复到 set 前的值)。
    """
    return _trace_id_var.set(trace_id or None)


def get_trace_id() -> str | None:
    """读取当前上下文的 trace_id；无则返回 None。"""
    return _trace_id_var.get()


def reset_trace_id(token) -> None:  # type: ignore[no-untyped-def]
    """恢复 set 之前的 trace_id (配套 set_trace_id 一起使用)。"""
    _trace_id_var.reset(token)


def set_start_time(ts: float) -> None:
    """main.py lifespan 启动时调用，覆盖默认的模块导入时间。"""
    global _START_TIME
    _START_TIME = ts


def uptime_s() -> float:
    """距进程启动的秒数（float）。"""
    return time.time() - _START_TIME


def log_event(event: str, **fields: Any) -> None:
    """统一事件打点入口。

    Args:
        event: 事件名（kebab-case 推荐）
        **fields: 任意 key=value 字段（必含 trace_id, level 由 logger 注入）

    v0.7 Batch 1 变更: 由 ``logger.info(event, extra=payload)`` 改为
    ``logger.bind(**payload).info(event)`` —— 后者把 payload 平铺到
    record["extra"] 顶层, 配合 logging_config.serialize=True 让
    ``jq '.record.extra.method'`` 直接命中, 不再嵌套 .record.extra.extra。

    自动注入: 若调用方未传 trace_id, 用 get_trace_id() 兜底,
    实现"业务代码不传也能关联"的契约 (PRD §5.3 兜底语义)。
    """
    try:
        if "trace_id" not in fields or not fields["trace_id"]:
            ctx = get_trace_id()
            if ctx:
                fields["trace_id"] = ctx
            else:
                fields.setdefault("trace_id", "")
        fields.setdefault("event", event)
        # bind 把所有 key 平铺到 record["extra"]; message 段记 event 名
        logger.bind(**fields).info(event)
    except Exception:
        # 日志失败永不阻塞业务
        pass


__all__ = [
    "get_trace_id",
    "log_event",
    "reset_trace_id",
    "set_start_time",
    "set_trace_id",
    "uptime_s",
]

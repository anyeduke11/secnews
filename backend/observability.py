"""Phase 5 可观测性 - 统一事件打点。

设计
----
- 单个入口 ``log_event(event, **fields)`` 封装 logger.info
- 所有事件带 ``event=<name>`` 字段便于 grep / 过滤
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
"""
from __future__ import annotations

import time
from typing import Any, Optional

from backend.logging_config import logger

# 进程级启动时间（首次访问时记录；可在 main.py lifespan 覆盖）
_START_TIME: float = time.time()


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

    用法
    ----
    >>> log_event("cache_hit", key="hotspots:list:ai:7d", cache_name="list")
    """
    try:
        # 把 event 注入 extra，自动序列化到 JSON
        payload = {"event": event, **fields}
        logger.info(event, extra=payload)
    except Exception:
        # 日志失败永不阻塞业务
        pass


__all__ = ["log_event", "set_start_time", "uptime_s"]

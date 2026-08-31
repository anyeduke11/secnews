"""Phase 4 中间件。

- :class:`TraceIDMiddleware`  每个请求生成 / 透传 ``X-Trace-Id``，写入
  ``request.state.trace_id``，由 exception handler 读取后回写到响应。

设计
----
- 不阻塞业务；只做 trace_id 注入 + duration 记录
- 现有 app 仍兼容（无 trace_id 头时生成 UUIDv4）
- 排除 health 端点（避免日志噪音）

v0.7 Observability Batch 1 (PRD §5.3): 在 dispatch 入口 set_trace_id,
业务代码 (LLM 记录 / job_runs / agent_runs 写入) 任意位置 get_trace_id()
即拿到当前请求关联键, 实现跨边界串联。finally reset_trace_id 避免污染。

v0.7 Observability Batch ③ (PRD §5.3): 在响应收尾调 record_api_call,
把每次 API 调用的 trace_id / method / path_template / status / duration_ms
 写到 api_events 表 — 供 dashboard 查询与阈值扫. 失败 swallow, 永不阻塞响应.
"""
from __future__ import annotations

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.observability import log_event, reset_trace_id, set_trace_id
from backend.observability_records import record_api_call

# Header that clients can pass to participate in distributed tracing
TRACE_HEADER = "X-Trace-Id"


class TraceIDMiddleware(BaseHTTPMiddleware):
    """注入 trace_id + 记录 duration。"""

    def __init__(self, app: ASGIApp, *, exclude_paths: list[str] | None = None):
        super().__init__(app)
        self.exclude_paths = set(exclude_paths or [])

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get(TRACE_HEADER) or uuid.uuid4().hex
        request.state.trace_id = trace_id
        token = set_trace_id(trace_id)

        # v0.7 Batch ③: 路由模板 (FastAPI route.path), 不是 raw URL;
        # raw URL 含 query string 会导致维度爆炸.
        route = request.scope.get("route")
        path_template = getattr(route, "path", request.url.path)

        log_event(
            "api_request",
            method=request.method,
            path=request.url.path,
            trace_id=trace_id,
        )

        # 记录 health 检查路径不写入 duration log
        if request.url.path in self.exclude_paths:
            try:
                response = await call_next(request)
            finally:
                reset_trace_id(token)
            response.headers[TRACE_HEADER] = trace_id
            return response

        start = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            log_event(
                "api_response",
                method=request.method,
                path=request.url.path,
                status=500,
                duration_ms=round(duration_ms, 2),
                trace_id=trace_id,
                error=type(e).__name__,
            )
            # v0.7 Batch ③: 异常路径同样落表 (status=500, error=异常名)
            record_api_call(
                trace_id=trace_id,
                method=request.method,
                path_template=path_template,
                status=500,
                duration_ms=round(duration_ms, 2),
                error=f"{type(e).__name__}: {e}",
            )
            reset_trace_id(token)
            raise

        duration_ms = (time.time() - start) * 1000
        response.headers[TRACE_HEADER] = trace_id
        response.headers["X-Duration-Ms"] = f"{duration_ms:.2f}"
        log_event(
            "api_response",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
            trace_id=trace_id,
        )
        # v0.7 Batch ③: 正常路径落表 (status=response.status_code)
        record_api_call(
            trace_id=trace_id,
            method=request.method,
            path_template=path_template,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        reset_trace_id(token)
        return response


__all__ = ["TRACE_HEADER", "TraceIDMiddleware"]

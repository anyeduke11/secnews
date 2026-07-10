"""Phase 4 中间件。

- :class:`TraceIDMiddleware`  每个请求生成 / 透传 ``X-Trace-Id``，写入
  ``request.state.trace_id``，由 exception handler 读取后回写到响应。

设计
----
- 不阻塞业务；只做 trace_id 注入 + duration 记录
- 现有 app 仍兼容（无 trace_id 头时生成 UUIDv4）
- 排除 health 端点（避免日志噪音）
"""
from __future__ import annotations

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.observability import log_event


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

        log_event(
            "api_request",
            method=request.method,
            path=request.url.path,
            trace_id=trace_id,
        )

        # 记录 health 检查路径不写入 duration log
        if request.url.path in self.exclude_paths:
            response = await call_next(request)
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
        return response


__all__ = ["TraceIDMiddleware", "TRACE_HEADER"]

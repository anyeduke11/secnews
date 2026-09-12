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

P0 安全项 (FIRST_PRINCIPLES_ANALYSIS_2026-09-11 §0.1): :class:`TokenAuthMiddleware`
最小 token 鉴权 — env ``HOTSPOT_API_TOKEN`` 设置时对所有 ``/api/*`` 请求校验
``X-Hotspot-Token`` 头 (常量时间比较), 不匹配 401; env 未设置时完全关闭
(默认关闭, 不破坏现有前端/测试)。豁免路径默认含 ``/api/health``。
"""
from __future__ import annotations

import os
import secrets
import time
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.observability import log_event, reset_trace_id, set_trace_id
from backend.observability_records import record_api_call
from backend.services.observability_sampling import should_record_api_event

# Header that clients can pass to participate in distributed tracing
TRACE_HEADER = "X-Trace-Id"

# Token 鉴权 (P0): 头名 / env 键名 / 默认豁免路径
API_TOKEN_HEADER = "X-Hotspot-Token"
API_TOKEN_ENV = "HOTSPOT_API_TOKEN"
API_TOKEN_EXEMPT_PATHS = ["/api/health"]


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
            # v0.7 Batch ③: 异常路径同样落表 (status=500, error=异常名).
            # v0.7 Batch ⑧ D4: 5xx 默认 error_rate_pct=100% (保 error_rate 精度);
            # 双层防御 (与正常路径一致): 外层再 swallow, 不阻塞 raise.
            try:
                if should_record_api_event(status=500, duration_ms=duration_ms):
                    record_api_call(
                        trace_id=trace_id,
                        method=request.method,
                        path_template=path_template,
                        status=500,
                        duration_ms=round(duration_ms, 2),
                        error=f"{type(e).__name__}: {e}",
                    )
            except Exception as _obs_e:
                log_event("api_observability_swallowed", level="debug",
                          trace_id=trace_id, error=str(_obs_e))
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
        # v0.7 Batch ③: 正常路径落表 (status=response.status_code).
        # v0.7 Batch ⑧ D4: 成功路径按 success_rate_pct 采样 (默认 10%),
        # 慢请求 (>= slow_threshold_ms) 按 slow_rate_pct (默认 100%) 保留;
        # 双层防御: record_api_call 内部 try/except 已 swallow; 此处外层
        # 再包一道确保任何诡异路径 (例如被 monkey-patch 抛异常) 都不阻塞响应.
        try:
            if should_record_api_event(
                status=response.status_code, duration_ms=duration_ms
            ):
                record_api_call(
                    trace_id=trace_id,
                    method=request.method,
                    path_template=path_template,
                    status=response.status_code,
                    duration_ms=round(duration_ms, 2),
                )
        except Exception as _obs_e:
            log_event("api_observability_swallowed", level="debug",
                      trace_id=trace_id, error=str(_obs_e))
        reset_trace_id(token)
        return response


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """P0 最小 token 鉴权 — env 启用, ``/api/*`` 校验 ``X-Hotspot-Token``。

    - ``HOTSPOT_API_TOKEN`` 未设置/为空 → 完全关闭 (直通, 默认状态)
    - 已设置: ``/api/*`` 必须带匹配 token 头, 否则 401; 豁免路径直通
    - 非 ``/api/`` 前缀 (首页/docs/static) 不校验
    - env 每请求读取, 便于测试 monkeypatch 与运行期热切换
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        header: str = API_TOKEN_HEADER,
        exempt_paths: list[str] | None = None,
    ):
        super().__init__(app)
        self.header = header
        self.exempt_paths = set(exempt_paths if exempt_paths is not None else API_TOKEN_EXEMPT_PATHS)

    async def dispatch(self, request: Request, call_next) -> Response:
        expected = os.getenv(API_TOKEN_ENV, "")
        if not expected:
            return await call_next(request)
        path = request.url.path
        if path in self.exempt_paths or not path.startswith("/api/"):
            return await call_next(request)
        supplied = request.headers.get(self.header, "")
        # encode 为 bytes 再比较: compare_digest 对非 ASCII str 抛 TypeError → 500
        if supplied and secrets.compare_digest(
            supplied.encode("utf-8"), expected.encode("utf-8")
        ):
            return await call_next(request)
        log_event(
            "api_auth_rejected",
            method=request.method,
            path=path,
        )
        return JSONResponse(
            status_code=401,
            content={"detail": "missing or invalid API token"},
        )


__all__ = [
    "API_TOKEN_ENV",
    "API_TOKEN_EXEMPT_PATHS",
    "API_TOKEN_HEADER",
    "TRACE_HEADER",
    "TokenAuthMiddleware",
    "TraceIDMiddleware",
]

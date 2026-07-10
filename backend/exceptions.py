"""统一异常体系 + FastAPI 异常处理器

- 定义业务异常基类 HotspotException 及常用子类
- register_exception_handlers(app) 把所有异常统一为
    {code, message, trace_id, version} 响应体（Phase 4 加 version）
- trace_id 优先从 ``request.state.trace_id`` 读（由 TraceIDMiddleware 注入）
"""
import logging
import uuid
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# 使用 stdlib logging 作为底层接收器（loguru 在 logging_config.setup() 中接管）
logger = logging.getLogger(__name__)

# API 版本号（与 main.py FastAPI(... version=...) 保持一致）
API_VERSION = "1.2.0"


class HotspotException(Exception):
    """所有业务异常的基类。"""

    def __init__(self, code: str, message: str, http_status: int = 500):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


class InvalidParamException(HotspotException):
    def __init__(self, message: str = "Invalid parameter"):
        super().__init__("INVALID_PARAM", message, 400)


class NotFoundException(HotspotException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__("NOT_FOUND", message, 404)


class RateLimitedException(HotspotException):
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__("RATE_LIMITED", message, 429)


class InternalException(HotspotException):
    def __init__(self, message: str = "Internal server error"):
        super().__init__("INTERNAL", message, 500)


class SourceUnavailableException(HotspotException):
    def __init__(self, message: str = "Source unavailable"):
        super().__init__("SOURCE_UNAVAILABLE", message, 503)


class QualityGateFailed(HotspotException):
    """Phase 3.5: 严格模式下，质量评分低于阈值，item 被拒绝入库。

    不映射到 HTTP（属于采集层内部错误，HTTP 422 在 Phase 4 才用到）。
    """

    def __init__(
        self,
        message: str = "Quality gate failed",
        *,
        item_id: str = "",
        score: int = 0,
        flags: Optional[list[str]] = None,
    ):
        super().__init__("QUALITY_GATE_FAILED", message, 422)
        self.item_id = item_id
        self.score = score
        self.flags = list(flags or [])


def _get_trace_id(request: Request) -> str:
    """从 request.state 读 trace_id；无则生成新 UUID。"""
    tid = getattr(request.state, "trace_id", None)
    return tid or uuid.uuid4().hex


def _err_response(
    request: Request,
    *,
    code: str,
    message: str,
    status: int,
) -> JSONResponse:
    """统一构造错误响应：{code, message, trace_id, version}。"""
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "trace_id": _get_trace_id(request),
            "version": API_VERSION,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI app。"""

    @app.exception_handler(HotspotException)
    async def hotspot_exception_handler(request: Request, exc: HotspotException):
        trace_id = _get_trace_id(request)
        logger.warning(
            "hotspot exception: %s - %s",
            exc.code,
            exc.message,
            extra={"trace_id": trace_id},
        )
        return _err_response(
            request, code=exc.code, message=exc.message, status=exc.http_status
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        trace_id = _get_trace_id(request)
        logger.error(
            "unhandled exception: %s",
            exc,
            extra={"trace_id": trace_id},
            exc_info=True,
        )
        return _err_response(
            request,
            code="INTERNAL",
            message="Internal server error",
            status=500,
        )


__all__ = [
    "HotspotException",
    "InvalidParamException",
    "NotFoundException",
    "RateLimitedException",
    "InternalException",
    "SourceUnavailableException",
    "QualityGateFailed",
    "register_exception_handlers",
]

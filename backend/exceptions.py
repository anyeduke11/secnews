"""统一异常体系 + FastAPI 异常处理器

- 定义业务异常基类 HotspotException 及常用子类
- register_exception_handlers(app) 把所有异常统一为
    {code, message, trace_id, version} 响应体（Phase 4 加 version）
- D13 (2026-09-12): 补注册 StarletteHTTPException (覆盖 FastAPI HTTPException)
    与 RequestValidationError handler, 消灭 FastAPI 默认嵌套 {detail:{...}}
    与扁平 envelope 并存的"两套错误响应体"
- trace_id 优先从 ``request.state.trace_id`` 读（由 TraceIDMiddleware 注入）
"""
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

# API 版本号: 单一来源 backend/version.py (main.py FastAPI(version=...) 同源)
from backend.version import APP_VERSION as API_VERSION


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


class ConflictException(HotspotException):
    """状态冲突（未初始化 / 未解锁 / 禁止重复操作等）→ 409。"""

    def __init__(self, message: str = "Conflict"):
        super().__init__("CONFLICT", message, 409)


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
        flags: list[str] | None = None,
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
    headers: dict[str, str] | None = None,
    extras: dict | None = None,
) -> JSONResponse:
    """统一构造错误响应：{code, message, trace_id, version[, ...extras]}。

    extras: HTTPException detail dict 中的附加结构化字段 (如
    current_revision / valid_modes), 平铺到顶层避免信息丢失。
    """
    content: dict = {
        "code": code,
        "message": message,
        "trace_id": _get_trace_id(request),
        "version": API_VERSION,
    }
    if extras:
        content.update(extras)
    return JSONResponse(status_code=status, content=content, headers=headers)


# D13: HTTP 状态码 → 契约错误码映射 (契约 8 错误码; 400 归 E_VALIDATION)
_STATUS_TO_CODE: dict[int, str] = {
    400: "E_VALIDATION",
    401: "E_AUTH",
    403: "E_FORBIDDEN",
    404: "E_NOT_FOUND",
    409: "E_CONFLICT",
    422: "E_VALIDATION",
    429: "E_RATE_LIMIT",
}


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI app。"""

    @app.exception_handler(HotspotException)
    async def hotspot_exception_handler(request: Request, exc: HotspotException):
        logger.warning(
            "hotspot exception: {} - {}",
            exc.code,
            exc.message,
        )
        return _err_response(
            request, code=exc.code, message=exc.message, status=exc.http_status
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """D13: HTTPException 统一为扁平 envelope (FastAPI HTTPException 是其子类)。

        detail 为 dict 且含 code 时优先用其值 (既有的
        HTTPException(404, detail={"message": ...}) 调用点平滑迁移)。
        """
        code = _STATUS_TO_CODE.get(exc.status_code, "E_INTERNAL")
        message = code
        extras: dict = {}
        if isinstance(exc.detail, dict):
            extras = {
                k: v for k, v in exc.detail.items() if k not in ("code", "message")
            }
            if exc.detail.get("code"):
                code = str(exc.detail["code"])
            message = str(exc.detail.get("message") or code)
        elif exc.detail:
            message = str(exc.detail)
        logger.warning(
            "http exception: {} {} - {}",
            exc.status_code,
            code,
            message,
        )
        return _err_response(
            request,
            code=code,
            message=message,
            status=exc.status_code,
            headers=exc.headers,
            extras=extras,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """D13: pydantic 422 校验错误同样输出扁平 envelope (E_VALIDATION)。"""
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        message = f"validation failed: {loc}: {first.get('msg', 'invalid')}" if loc else "validation failed"
        logger.warning("validation error: {}", message)
        return _err_response(
            request, code="E_VALIDATION", message=message, status=422
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.opt(exception=exc).error("unhandled exception: {}", exc)
        return _err_response(
            request,
            code="INTERNAL",
            message="Internal server error",
            status=500,
        )


__all__ = [
    "ConflictException",
    "HotspotException",
    "InternalException",
    "InvalidParamException",
    "NotFoundException",
    "QualityGateFailed",
    "RateLimitedException",
    "SourceUnavailableException",
    "register_exception_handlers",
]

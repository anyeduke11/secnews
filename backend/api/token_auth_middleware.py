"""TokenAuthMiddleware — P0 最小 token 鉴权 (DEV-0287 D5 拆分自 middleware.py)。

- ``HOTSPOT_API_TOKEN`` 未设置/为空 → 完全关闭 (直通, 默认状态)
- 已设置: **除公共资产外全部入口**须带匹配 token 头, 否则 401:
  * ``/api/*`` — 既有行为
  * ``/mcp/sse`` 等非 /api/ 端点 — v0.8.6 P0-3 (审计 S1: 此前
    非 /api/ 整类直通, MCP 19 工具含写绕过唯一鉴权层)
  * ``/docs`` / ``/openapi.json`` — 接口自描述同样属暴露面
  * 公共资产放行: ``/`` (SPA 首页壳)、favicon、/assets/、/static/
    (静态资源本身无敏感数据; 前端 fetch 统一走 /api/* 携 token)
- env 每请求读取, 便于测试 monkeypatch 与运行期热切换
"""
from __future__ import annotations

import os
import secrets

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.observability import log_event

# Token 鉴权 (P0): 头名 / env 键名 / 默认豁免路径
API_TOKEN_HEADER = "X-Hotspot-Token"
API_TOKEN_ENV = "HOTSPOT_API_TOKEN"
API_TOKEN_EXEMPT_PATHS = ["/api/health"]

# v0.8.6 P0-3 (审计 S1 / D7 全入口覆盖): 非 /api/ 路径不再是"直通整类"。
# 仅放行单用户 SPA 必需的公共资产; /mcp/sse (19 工具含写)、/docs、
# /openapi.json 在 token 启用时一并校验 — 设了 token 就锁住全部入口。
# 判定: 精确匹配 "/" 与 favicon; 其余按公共资产目录前缀 (静态资源经
# FastAPI StaticFiles 挂载, 前缀集合固定)。
_PUBLIC_PATH_PREFIXES = ("/assets/", "/static/")
_PUBLIC_PATHS = frozenset({"/", "/favicon.ico", "/favicon.svg"})


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """P0 最小 token 鉴权 — env 启用, 全入口校验 ``X-Hotspot-Token``。"""

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

    @staticmethod
    def _is_public(path: str) -> bool:
        """单用户 SPA 必需的公共资产 (token 启用时仍放行)。"""
        return path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PATH_PREFIXES)

    async def dispatch(self, request: Request, call_next) -> Response:
        expected = os.getenv(API_TOKEN_ENV, "")
        if not expected:
            return await call_next(request)
        path = request.url.path
        if path in self.exempt_paths or self._is_public(path):
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
    "TokenAuthMiddleware",
]

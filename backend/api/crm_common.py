"""CRM 路由共享件: v1 单操作者 Token 鉴权 (PRD §4 Auth)。

约定: 环境变量 ``HOTSPOT_CRM_TOKEN`` 未设置 = 本地单机模式放行 (响应头
``X-CRM-Auth: disabled`` 提示); 设置后要求请求头 ``X-CRM-Token`` 常量时间比对。
多租户/角色为 PRD §5 明确非目标。
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request

TOKEN_HEADER = "X-CRM-Token"


async def require_crm_token(request: Request) -> None:
    expected = os.environ.get("HOTSPOT_CRM_TOKEN", "")
    if not expected:
        request.state.crm_auth = "disabled"
        return
    provided = request.headers.get(TOKEN_HEADER, "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail={"message": "CRM token 无效或缺失"})


__all__ = ["TOKEN_HEADER", "require_crm_token"]

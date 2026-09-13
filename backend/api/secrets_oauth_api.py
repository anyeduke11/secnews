"""OAuth 解锁 API — 拆自 ``backend/api/secrets.py`` (Batch 3 R3, D1 Batch ⑧)。

- ``POST /api/secrets/unlock-with-oauth``  OAuth access_token 解锁 (不解密, 双因素)
- ``GET  /api/secrets/oauth-config``       前端读取 OAuth 启动参数
"""
from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.secrets_lifecycle_api import _err_to_http
from backend.observability_records import record_audit
from backend.services.secrets_service import SecretsService

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


class UnlockWithOAuthRequest(BaseModel):
    """D1 (Batch ⑧): OAuth 解锁请求 — 用 OAuth access_token 证明身份。

    不需要 master_key; 用户需先在前端完成 OAuth 授权跳转, 拿到 token。
    """
    token: str = Field(..., min_length=10, description="OAuth access_token")
    role: str = Field("admin", description="密钥角色 (admin|user)")


class OAuthConfigResponse(BaseModel):
    """D1: 前端读取以决定是否显示 OAuth 解锁按钮 + 启动授权跳转。"""
    enabled: bool
    client_id: str
    redirect_uri: str
    authorize_url: str  # 前端跳转 URL (构造)
    scope: str


@router.post("/unlock-with-oauth")
async def unlock_with_oauth(req: UnlockWithOAuthRequest):
    """D1 (Batch ⑧): OAuth 解锁 — 跳过 master_key, 用 OAuth access_token + allowlist。

    流程: token → CloudBase OAuth userinfo → email allowlist 校验 → audit 授权通路。
    **不解密** (master_key 仍是密钥, OAuth 仅是身份) — 这是"双因素"语义。
    """
    from backend.services.oauth_provider import OAuthVerificationError

    svc = SecretsService()
    try:
        result = await asyncio.to_thread(svc.unlock_with_oauth, req.token, req.role)
    except OAuthVerificationError as e:
        record_audit(actor="oauth", action="llm_secrets.unlock_oauth_failed",
                     detail={"role": req.role, "reason": str(e)})
        raise HTTPException(401, f"INVALID_OAUTH_TOKEN: {e}")
    except Exception as e:
        raise _err_to_http(e)

    record_audit(actor="oauth", action="llm_secrets.unlock_oauth",
                 detail={"role": req.role, "email": result.get("oauth_user", "")})
    return {"version": "1.0", **result}


@router.get("/oauth-config", response_model=OAuthConfigResponse)
async def get_oauth_config():
    """D1: 前端读取 OAuth 启动参数。

    安全: 不返回 client_secret; 仅当 HOTSPOT_OAUTH_CLIENT_ID 配齐才 enabled=True。
    """
    client_id = os.environ.get("HOTSPOT_OAUTH_CLIENT_ID", "").strip()
    redirect_uri = os.environ.get("HOTSPOT_OAUTH_REDIRECT_URI", "").strip()
    authorize_base = os.environ.get("HOTSPOT_OAUTH_AUTHORIZE_URL", "").strip()
    scope = os.environ.get("HOTSPOT_OAUTH_SCOPE", "openid profile email").strip()
    enabled = bool(client_id and redirect_uri and authorize_base)
    # 拼授权 URL (前端跳转), CSRF state 由前端生成
    authorize_url = ""
    if enabled:
        authorize_url = (
            f"{authorize_base}?response_type=code"
            f"&client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scope}"
        )
    return OAuthConfigResponse(
        enabled=enabled,
        client_id=client_id,
        redirect_uri=redirect_uri,
        authorize_url=authorize_url,
        scope=scope,
    )

"""密钥生命周期 API — 拆自 ``backend/api/secrets.py`` (Batch 3 R3 行数收缩)。

- ``GET  /api/secrets/status``  主密钥初始化 + unlock 状态
- ``POST /api/secrets/setup``   首次设置主密钥 (一次性)
- ``POST /api/secrets/unlock``  解锁 (30 分钟窗口)
- ``GET  /api/secrets/unlock``  解锁状态查询
- ``POST /api/secrets/lock``    立即锁定

``_err_to_http`` 是本域共用的错误→HTTP 映射, 由 oauth/keys/reveal/rotation
子文件复用 (单向 sibling import, 无循环)。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.crypto import InvalidMasterKeyError, WeakMasterKeyError
from backend.exceptions import HotspotException
from backend.observability_records import record_audit
from backend.services.secrets_service import SecretsService

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class SetupRequest(BaseModel):
    # P4-9: min_length 与 crypto.MIN_MASTER_KEY_LENGTH (12) 对齐 —
    # 此前 8 vs 12 校验不一致, 8-11 字符能过 API 却在 crypto 层被拒
    master_key: str = Field(..., min_length=12, description="主密钥 (>= 12 字符)")
    role: str = Field("admin", description="密钥角色 (admin|user)")


class UnlockRequest(BaseModel):
    master_key: str = Field(..., description="主密钥")
    role: str = Field("admin", description="密钥角色 (admin|user)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _err_to_http(e: Exception) -> HTTPException:
    """统一错误 → HTTP 状态码（结构化映射, 不做消息文本匹配）。"""
    if isinstance(e, InvalidMasterKeyError):
        return HTTPException(status_code=401, detail={"message": "主密钥错误"})
    if isinstance(e, WeakMasterKeyError):
        return HTTPException(status_code=400, detail={"message": str(e)})
    if isinstance(e, HotspotException):
        return HTTPException(status_code=e.http_status, detail={"message": e.message})
    return HTTPException(status_code=400, detail={"message": str(e)})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/status")
async def get_status():
    """主密钥初始化状态 + unlock 状态。"""
    svc = SecretsService()
    setup = await asyncio.to_thread(svc.is_master_key_setup)
    status = await asyncio.to_thread(svc.unlock_status)
    return {
        "version": "1.0",
        "setup": setup,
        **status,
    }


@router.post("/setup", status_code=201)
async def setup_master_key(req: SetupRequest):
    """首次设置主密钥 (一次性, 禁止重置)。T4: role=admin|user."""
    svc = SecretsService()
    try:
        result = await asyncio.to_thread(svc.setup_master_key, req.master_key, req.role)
    except Exception as e:
        raise _err_to_http(e)
    record_audit(actor="web", action="llm_secrets.setup",
                 detail={"encryption_key_id": result.get("id"), "role": req.role})
    return {
        "version": "1.0",
        "encryption_key": result,
    }


@router.post("/unlock")
async def unlock(req: UnlockRequest):
    """30 分钟解锁。T4: role=admin|user."""
    svc = SecretsService()
    try:
        result = await asyncio.to_thread(svc.unlock, req.master_key, req.role)
    except Exception as e:
        raise _err_to_http(e)
    record_audit(actor="web", action="llm_secrets.unlock",
                 detail={"ttl_seconds": result.get("ttl_seconds"), "role": req.role})
    return {
        "version": "1.0",
        **result,
    }


@router.get("/unlock")
async def unlock_status(role: str = "admin"):
    """查询 unlock 状态 + 剩余秒数。T4: role=admin|user."""
    svc = SecretsService()
    return await asyncio.to_thread(svc.unlock_status, role)


@router.post("/lock")
async def lock_now():
    """立即清空 unlock 状态。"""
    svc = SecretsService()
    record_audit(actor="web", action="llm_secrets.lock")
    return await asyncio.to_thread(svc.lock)

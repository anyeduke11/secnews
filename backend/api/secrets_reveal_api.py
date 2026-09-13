"""密钥 reveal / 连通性测试 API — 拆自 ``backend/api/secrets.py`` (Batch 3 R3)。

- ``POST /api/secrets/{id}/reveal``  取明文 (每次现场提交 master_key, 强审计)
- ``POST /api/secrets/{id}/test``    测试连通性
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.api.secrets_lifecycle_api import _err_to_http
from backend.observability_records import record_audit
from backend.services.secrets_service import SecretsService

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


class RevealRequest(BaseModel):
    """reveal — 每次取明文都必须现场提交主密钥（不依赖 unlock 窗口）。"""
    master_key: str = Field(..., description="主密钥")


@router.post("/{secret_id}/reveal")
async def reveal(secret_id: int, req: RevealRequest):
    """返回明文 api_key (每次都必须现场提交并验证 master_key)。

    v0.7.x Batch ⑥: reveal 是高敏感操作, 强审计 — audit_log 必写, detail
    含 secret_id 但不含 api_key 明文 (永远不进 audit_log)。
    """
    svc = SecretsService()
    try:
        result = await asyncio.to_thread(svc.reveal, int(secret_id), req.master_key)
    except Exception as e:
        raise _err_to_http(e)
    record_audit(actor="web", action="llm_secrets.reveal",
                 target=f"secret:{secret_id}",
                 detail={"secret_id": secret_id, "provider": result.get("provider", "")})
    return {
        "version": "1.0",
        **result,
    }


@router.post("/{secret_id}/test")
async def test_connection(secret_id: int):
    """测试连通性 (Phase 41 Q4)。"""
    svc = SecretsService()
    try:
        result = await asyncio.to_thread(svc.test_connection, int(secret_id))
    except Exception as e:
        raise _err_to_http(e)
    record_audit(actor="web", action="llm_secrets.test",
                 target=f"secret:{secret_id}",
                 detail={"secret_id": secret_id, "ok": bool(result.get("ok")),
                         "latency_ms": result.get("latency_ms")})
    return {
        "version": "1.0",
        **result,
    }

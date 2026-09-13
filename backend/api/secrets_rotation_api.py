"""主密钥轮换 + 导入/导出 API — 拆自 ``backend/api/secrets.py`` (Batch 3 R3)。

- ``GET  /api/secrets/rotation-status``  轮换状态 (age + should_rotate 提醒)
- ``POST /api/secrets/rotate``           轮换主密钥 (重加密全部密文, 事务保证)
- ``GET  /api/secrets/export``           导出加密 JSON 文件
- ``POST /api/secrets/import``           导入加密 JSON 文件
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response as FastResponse
from pydantic import BaseModel, Field

from backend.api.secrets_lifecycle_api import _err_to_http
from backend.observability_records import record_audit
from backend.services.secrets_service import SecretsService

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


class RotateRequest(BaseModel):
    """v0.7.x Batch ⑥: 轮换主密钥 — 重加密全部密文 (llm_secrets + webdav)。

    重加密过程走事务, 部分失败 ROLLBACK, 旧密钥仍可用。
    旧密钥错误 → 401 INVALID_MASTER_KEY; 新密钥太弱 → 400 WEAK_MASTER_KEY。
    """
    old_key: str = Field(..., min_length=12, description="旧主密钥")
    new_key: str = Field(..., min_length=12, description="新主密钥")
    actor: str = Field("web", description="操作者 (web / system / agent:*)")


class ImportRequest(BaseModel):
    """导入 — base64 编码的导出文件。"""
    payload_b64: str = Field(..., description="base64 编码的导出文件内容")
    master_key: str = Field(..., description="主密钥")


@router.get("/rotation-status")
async def rotation_status(role: str = "admin"):
    """T3: 查询主密钥轮换状态 (age + should_rotate 提醒)."""
    svc = SecretsService()
    return await asyncio.to_thread(svc.rotation_status)


@router.post("/rotate", status_code=200)
async def rotate_master_key(req: RotateRequest):
    """v0.7.x Batch ⑥: 轮换主密钥 (重加密全部密文)。

    旧密钥错误 → 401; 新密钥太弱 → 400; 重加密部分失败 → ROLLBACK
    (由 SecretsService.rotate_master_key 内部事务保证)。
    """
    svc = SecretsService()
    try:
        result = await asyncio.to_thread(svc.rotate_master_key, req.old_key, req.new_key)
    except Exception as e:
        raise _err_to_http(e)
    record_audit(actor=req.actor, action="llm_secrets.rotate",
                 detail={"reencrypted_secrets": result.get("reencrypted_secrets", 0),
                         "reencrypted_webdav": result.get("reencrypted_webdav", 0)})
    return {
        "version": "1.0",
        "status": "ok",
        **result,
    }


@router.get("/export")
async def export_secrets(master_key: str = ""):
    """导出加密 JSON 文件 (Phase 41 Q3)。"""
    svc = SecretsService()
    if not master_key:
        raise HTTPException(status_code=400, detail={"message": "master_key 必填"})
    try:
        data = await asyncio.to_thread(svc.export, master_key)
    except Exception as e:
        raise _err_to_http(e)
    # 返回 application/octet-stream 触发浏览器下载
    filename = f"secrets-export-{int(__import__('time').time())}.json"
    return FastResponse(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/import")
async def import_secrets(req: ImportRequest):
    """导入加密 JSON 文件 (Phase 41 Q3)。"""
    import base64
    svc = SecretsService()
    try:
        payload = base64.b64decode(req.payload_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"message": f"base64 解析失败: {e}"})
    try:
        result = await asyncio.to_thread(svc.import_from_bytes, payload, req.master_key)
    except Exception as e:
        raise _err_to_http(e)
    return {
        "version": "1.0",
        **result,
    }

"""密钥 CRUD API — 拆自 ``backend/api/secrets.py`` (Batch 3 R3 行数收缩)。

- ``GET    /api/secrets``       列表 (无明文, 含 unlocked 标记)
- ``POST   /api/secrets``       新增 (body 含 master_key)
- ``PATCH  /api/secrets/{id}``  更新 (改 api_key 需 master_key)
- ``DELETE /api/secrets/{id}``  删除
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from backend.api.secrets_lifecycle_api import _err_to_http
from backend.observability_records import record_audit
from backend.services.secrets_service import SecretsService

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class CreateSecretRequest(BaseModel):
    name: str = Field(..., max_length=120)
    model: str = Field(..., max_length=120)
    base_url: str = Field(..., max_length=300)
    # S4-1: provider 字段 (sensenova / dots.ai / openai / anthropic / ollama / 自定义),
    # 与 ai_hub _resolve_provider + secrets_service provider 路由联动; 默认空串向后兼容。
    provider: str = Field("", max_length=64, description="LLM provider 名 (sensenova / dots.ai / openai / anthropic / ollama / 自定义)")
    api_key: str = Field(..., description="明文 API key, 仅在传输/落库加密时短暂存在")
    master_key: str = Field(..., description="主密钥, 用于加密新条目")
    owner_role: str = Field("admin", description="归属角色 admin|user (B9-3 ACL)")


class UpdateSecretRequest(BaseModel):
    name: str | None = Field(None, max_length=120)
    model: str | None = Field(None, max_length=120)
    base_url: str | None = Field(None, max_length=300)
    provider: str | None = Field(None, max_length=64, description="LLM provider 名")
    api_key: str | None = None
    master_key: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("")
async def list_secrets(actor_role: str = "admin"):
    """列出 secret (元数据, 不含明文; 每条带 unlocked 标记).

    v0.7 Batch ⑨ B9-3: actor_role 透传到 service; user 角色只看 user-owned.
    默认 admin 保持向后兼容 (前端现仅 admin 角色).
    """
    svc = SecretsService()
    try:
        items, total = await asyncio.to_thread(svc.list_secrets, actor_role)
    except Exception as e:
        raise _err_to_http(e)
    return {
        "version": "1.0",
        "total": total,
        "items": items,
    }


@router.post("", status_code=201)
async def create_secret(req: CreateSecretRequest):
    """新增 secret (需要 master_key 现场加密)。"""
    svc = SecretsService()
    try:
        item = await asyncio.to_thread(
            svc.create_secret,
            name=req.name,
            model=req.model,
            base_url=req.base_url,
            api_key=req.api_key,
            master_key=req.master_key,
            provider=req.provider,
            owner_role=req.owner_role,
        )
    except Exception as e:
        raise _err_to_http(e)
    record_audit(actor="web", action="llm_secrets.create",
                 target=f"secret:{item['id']}",
                 detail={"secret_id": item["id"], "provider": item.get("provider", ""),
                         "name": item.get("name", "")})
    return {
        "version": "1.0",
        "item": item,
    }


@router.patch("/{secret_id}")
async def update_secret(secret_id: int, req: UpdateSecretRequest):
    """更新 secret; 改 api_key 必须传 master_key。"""
    svc = SecretsService()
    try:
        item = await asyncio.to_thread(
            svc.update_secret,
            int(secret_id),
            name=req.name,
            model=req.model,
            base_url=req.base_url,
            api_key=req.api_key,
            master_key=req.master_key,
            provider=req.provider,
        )
    except Exception as e:
        raise _err_to_http(e)
    fields_changed = sorted(
        f for f in ("name", "model", "base_url", "api_key", "provider")
        if getattr(req, f) is not None
    )
    record_audit(actor="web", action="llm_secrets.update",
                 target=f"secret:{item['id']}",
                 detail={"secret_id": item["id"], "fields_changed": fields_changed,
                         "api_key_changed": bool(req.api_key)})
    return {
        "version": "1.0",
        "item": item,
    }


@router.delete("/{secret_id}", status_code=204)
async def delete_secret(secret_id: int):
    """硬删除 secret。"""
    svc = SecretsService()
    try:
        await asyncio.to_thread(svc.delete_secret, int(secret_id))
    except Exception as e:
        raise _err_to_http(e)
    record_audit(actor="web", action="llm_secrets.delete",
                 target=f"secret:{secret_id}",
                 detail={"secret_id": secret_id})
    return Response(status_code=204)

"""Phase 41 密钥管理 API: 加密 + 30min unlock + CRUD + reveal + test + import/export。

路由
----
- ``GET    /api/secrets/status``                    主密钥是否初始化 + unlock 状态
- ``POST   /api/secrets/setup``                     首次设置主密钥 (一次性)
- ``POST   /api/secrets/unlock``                    解锁 (body: master_key)
- ``GET    /api/secrets/unlock``                    解锁状态查询
- ``POST   /api/secrets/lock``                      立即锁定
- ``GET    /api/secrets``                           列表 (无明文, 含 unlocked 标记)
- ``POST   /api/secrets``                           新增 (body 含 master_key)
- ``PATCH  /api/secrets/{id}``                      更新 (改 api_key 需 master_key)
- ``DELETE /api/secrets/{id}``                      删除
- ``POST   /api/secrets/{id}/reveal``               取得明文 (需提交 master_key 现场验证)
- ``POST   /api/secrets/{id}/test``                 测试连通性
- ``GET    /api/secrets/export``                    导出加密 JSON 文件
- ``POST   /api/secrets/import``                    导入加密 JSON 文件

安全
----
- master_key / api_key 不进日志
- 错误信息只回类型 (e.g. "主密钥错误"), 不回内部堆栈
- 400 / 401 / 404 / 423 Locked 用明确的状态码
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import Response as FastResponse
from pydantic import BaseModel, Field

from backend.crypto import InvalidMasterKeyError, WeakMasterKeyError
from backend.exceptions import HotspotException
from backend.logging_config import logger
from backend.services.secrets_service import SecretsService, _unlock_state

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class SetupRequest(BaseModel):
    # P4-9: min_length 与 crypto.MIN_MASTER_KEY_LENGTH (12) 对齐 —
    # 此前 8 vs 12 校验不一致, 8-11 字符能过 API 却在 crypto 层被拒
    master_key: str = Field(..., min_length=12, description="主密钥 (>= 12 字符)")


class UnlockRequest(BaseModel):
    master_key: str = Field(..., description="主密钥")


class CreateSecretRequest(BaseModel):
    name: str = Field(..., max_length=120)
    model: str = Field(..., max_length=120)
    base_url: str = Field(..., max_length=300)
    api_key: str = Field(..., description="明文 API key, 仅在传输/落库加密时短暂存在")
    master_key: str = Field(..., description="主密钥, 用于加密新条目")


class UpdateSecretRequest(BaseModel):
    name: str | None = Field(None, max_length=120)
    model: str | None = Field(None, max_length=120)
    base_url: str | None = Field(None, max_length=300)
    api_key: str | None = None
    master_key: str | None = None


class ImportRequest(BaseModel):
    """导入 — base64 编码的导出文件。"""
    payload_b64: str = Field(..., description="base64 编码的导出文件内容")
    master_key: str = Field(..., description="主密钥")


class RevealRequest(BaseModel):
    """reveal — 每次取明文都必须现场提交主密钥（不依赖 unlock 窗口）。"""
    master_key: str = Field(..., description="主密钥")


# Phase 42: admin reset 二次确认字符串 (在 setup 之外的紧急清空入口)
RESET_CONFIRM_STRING = "YES_RESET_ALL_SECRETS"


class ResetRequest(BaseModel):
    """admin reset — 二次确认, **不可恢复**。"""
    confirm: str = Field(..., description=f"必须等于 '{RESET_CONFIRM_STRING}' 才会执行")


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
    """首次设置主密钥 (一次性, 禁止重置)。"""
    svc = SecretsService()
    try:
        result = await asyncio.to_thread(svc.setup_master_key, req.master_key)
    except Exception as e:
        raise _err_to_http(e)
    return {
        "version": "1.0",
        "encryption_key": result,
    }


@router.post("/reset", status_code=200)
async def reset_all_secrets(req: ResetRequest):
    """**Admin 紧急清空** — 不可恢复。

    清空范围 (按顺序):
    1. ``secret_access_logs`` (audit 痕迹)
    2. ``llm_secrets`` (LLM 加密的 API key)
    3. ``sync_configs`` (webdav password 加密依赖 master_key, 一并清)
    4. ``sync_history`` + ``sync_states`` (跨端同步状态)
    5. ``encryption_keys`` (主密钥本身)
    6. 进程内 ``_unlock_state`` 缓存

    二次确认: ``confirm`` 字段必须等于 ``"YES_RESET_ALL_SECRETS"``。
    二次确认不通过 → 409 Conflict, 不做任何操作。

    **定位**: 这是「忘记主密码」时的逃生舱, 因此无法要求 master_key 作为
    凭证; 防滥用依赖两点 —— 服务默认仅监听 127.0.0.1 (见 config.host),
    以及本确认串。若显式绑定 0.0.0.0, 局域网内任何人都能触发此接口。

    **警告**: 调用后所有加密数据永久丢失, 需重新 setup + 重新录入 LLM 密钥。
    """
    from backend.repository.encryption_keys_repo import EncryptionKeyRepository
    from backend.repository.secrets_repo import SecretRepository
    from backend.repository.sync_configs_repo import SyncConfigRepository
    from backend.repository.sync_history_repo import SyncHistoryRepository
    from backend.repository.sync_states_repo import SyncStateRepository

    if req.confirm != RESET_CONFIRM_STRING:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "二次确认字符串不匹配; 想执行清空请传 confirm="
                    f"'{RESET_CONFIRM_STRING}'"
                )
            },
        )

    # 进程内 unlock state 先清, 避免后续操作还在用旧 fernet_key
    _unlock_state.clear()

    counts = {
        "access_logs_cleared": SecretRepository().clear_access_logs(),
        "llm_secrets_cleared": SecretRepository().delete_all(),
        "sync_configs_cleared": SyncConfigRepository().delete_all(),
    }
    # 清空 sync_history / sync_states (FK 到 sync_configs, 配对清)
    counts["sync_history_cleared"] = SyncHistoryRepository().prune_all()
    counts["sync_states_cleared"] = SyncStateRepository().clear_all()
    counts["encryption_key_cleared"] = EncryptionKeyRepository().delete_default()

    logger.warning(
        "admin reset: all secrets cleared",
        extra={"counts": str(counts)},
    )
    return {
        "version": "1.0",
        "reset": True,
        "counts": counts,
        "next_step": (
            "请重新调用 POST /api/secrets/setup 设置新主密钥, "
            "然后重新录入 LLM 密钥"
        ),
    }


@router.post("/unlock")
async def unlock(req: UnlockRequest):
    """30 分钟解锁。"""
    svc = SecretsService()
    try:
        result = await asyncio.to_thread(svc.unlock, req.master_key)
    except Exception as e:
        raise _err_to_http(e)
    return {
        "version": "1.0",
        **result,
    }


@router.get("/unlock")
async def unlock_status():
    """查询 unlock 状态 + 剩余秒数。"""
    svc = SecretsService()
    return await asyncio.to_thread(svc.unlock_status)


@router.post("/lock")
async def lock_now():
    """立即清空 unlock 状态。"""
    svc = SecretsService()
    return await asyncio.to_thread(svc.lock)


@router.get("")
async def list_secrets():
    """列出所有 secret (元数据, 不含明文; 每条带 unlocked 标记)。"""
    svc = SecretsService()
    try:
        items, total = await asyncio.to_thread(svc.list_secrets)
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
        )
    except Exception as e:
        raise _err_to_http(e)
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
        )
    except Exception as e:
        raise _err_to_http(e)
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
    return Response(status_code=204)


@router.post("/{secret_id}/reveal")
async def reveal(secret_id: int, req: RevealRequest):
    """返回明文 api_key (每次都必须现场提交并验证 master_key)。"""
    svc = SecretsService()
    try:
        result = await asyncio.to_thread(svc.reveal, int(secret_id), req.master_key)
    except Exception as e:
        raise _err_to_http(e)
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
    return {
        "version": "1.0",
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


__all__ = ["router"]

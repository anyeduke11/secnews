"""Admin 紧急清空 API — 拆自 ``backend/api/secrets.py`` (Batch 3 R3 行数收缩)。

- ``POST /api/secrets/reset``  不可恢复清空 (二次确认字符串 + 本机来源门禁)

安全语义逐字搬移: ``_require_local_or_admin`` 来源门禁 + 常数时间 token 比较
+ ``RESET_CONFIRM_STRING`` 二次确认, 均未改写。
"""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.logging_config import logger
from backend.observability_records import record_audit
from backend.services.secrets_service import _unlock_state

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


# Phase 42: admin reset 二次确认字符串 (在 setup 之外的紧急清空入口)
RESET_CONFIRM_STRING = "YES_RESET_ALL_SECRETS"

# 本机来源判定: 空 peer 与 "testclient" 来自 ASGI 进程内调用 (无真实 socket);
# 真实 uvicorn 连接总能拿到具体 host。
_LOCAL_PEERS = {"127.0.0.1", "::1", "::ffff:127.0.0.1", "testclient"}


def _require_local_or_admin(request: Request) -> None:
    """不可逆销毁类端点的来源门禁。

    原先唯一的防线是 docstring 里"服务默认仅监听 127.0.0.1"这一**假设**,
    而部署实况绑 0.0.0.0 时局域网任意主机都能一次清空全部密钥 —— 确认串
    又就写在源码里, 等于没有防线。这里改成校验请求**实际来源**:
    本机直连放行, 非本机必须带 HOTSPOT_ADMIN_TOKEN (常数时间比较)。
    """
    peer = (request.client.host if request.client else "") or ""
    if not peer or peer in _LOCAL_PEERS:
        return
    token = os.getenv("HOTSPOT_ADMIN_TOKEN", "").strip()
    supplied = request.headers.get("X-Admin-Token", "")
    if token and hmac.compare_digest(token, supplied):
        return
    raise HTTPException(
        status_code=403,
        detail={
            "message": (
                "不可逆清空仅限本机来源; 远程调用需配置环境变量 "
                "HOTSPOT_ADMIN_TOKEN 并携带 X-Admin-Token 请求头"
            )
        },
    )


class ResetRequest(BaseModel):
    """admin reset — 二次确认, **不可恢复**。"""
    confirm: str = Field(..., description=f"必须等于 '{RESET_CONFIRM_STRING}' 才会执行")


@router.post("/reset", status_code=200)
async def reset_all_secrets(req: ResetRequest, request: Request):
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
    凭证。防滥用依赖两点 —— ``confirm`` 二次确认 (防误触), 以及
    :func:`_require_local_or_admin` 的**来源门禁**: 本机回环直连放行,
    远程调用必须配置 HOTSPOT_ADMIN_TOKEN 并携带 X-Admin-Token。
    绑定 0.0.0.0 时局域网主机若无双因子, 得到 403 而不是清空成功。

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
            detail={"message": "二次确认字符串不匹配 (见 API 文档 / 源码常量 RESET_CONFIRM_STRING)"},
        )

    _require_local_or_admin(request)

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
    record_audit(actor="web", action="llm_secrets.reset",
                 detail={"counts": counts})
    return {
        "version": "1.0",
        "reset": True,
        "counts": counts,
        "next_step": (
            "请重新调用 POST /api/secrets/setup 设置新主密钥, "
            "然后重新录入 LLM 密钥"
        ),
    }

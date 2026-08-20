"""Phase 42 跨端配置同步 API: WebDAV 配置 + push/pull/bidirectional + 历史。

路由
----
- ``GET    /api/sync/status``           当前 sync_configs + status 摘要
- ``POST   /api/sync/config``           upsert WebDAV 配置 (含 master_key 用于加密)
- ``DELETE /api/sync/config``           删除配置 (同时清空 sync_states / history)
- ``POST   /api/sync/test``             测试 WebDAV 连通性 (webdav_password 明文)
- ``POST   /api/sync/push``             手动 push (body: master_key)
- ``POST   /api/sync/pull``             手动 pull (body: master_key)
- ``POST   /api/sync/bidirectional``    手动双向 (body: master_key)
- ``GET    /api/sync/history``          最近 50 条同步记录
- ``POST   /api/sync/auto``             开启/关闭自动同步 (body: enabled)
- ``GET    /api/sync/bundle/preview``   预览本机 bundle (debug; 不含 secrets 密文)

加密
----
- webdav_password 用 master_key + 独立 salt 加密 (Q1 决策: 独立加密字段)
  - 推导: PBKDF2-HMAC-SHA256(master_key, sync_configs.webdav_password_salt, iters)
  - 加密: Fernet(derived_key).encrypt(webdav_password)
- bundle 整体用 master_key + encryption_keys.salt 派生 fernet_key 加密 (Q4 + Q5)
- 跨端: 远端用同一 master_key + 同一 salt/iter 解密
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.crypto import InvalidMasterKeyError
from backend.repository.sync_configs_repo import SyncConfigRepository
from backend.repository.sync_history_repo import SyncHistoryRepository
from backend.repository.sync_states_repo import SyncStateRepository
from backend.services.sync_config_service import SyncConfigService
from backend.services.sync_service import SyncService
from backend.services.webdav_client import WebDAVClient

router = APIRouter(prefix="/api/sync", tags=["sync"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class UpsertConfigRequest(BaseModel):
    webdav_url: str = Field(..., min_length=1, max_length=500)
    webdav_username: str = Field(..., min_length=1, max_length=200)
    webdav_password: str | None = Field(default=None, min_length=1, max_length=500,
                                           description="WebDAV 应用密码 (明文, 加密后存库); 留空 = 不修改 (仅限已配置)")
    master_key: str = Field(..., min_length=8, description="主密钥; 验证身份 (已配置时) 或 加密 webdav password (首次)")
    remote_path: str = Field(default="/hotspot/config.json", max_length=300)
    auto_sync_enabled: bool = Field(default=False)
    auto_sync_interval_minutes: int = Field(default=10080, ge=10, le=10080 * 4)
    sync_frequency: str = Field(default="weekly", pattern="^(manual|daily|weekly|after_collect)$")


class PushRequest(BaseModel):
    master_key: str = Field(..., min_length=8)


class PullRequest(BaseModel):
    master_key: str = Field(..., min_length=8)


class BidirectionalRequest(BaseModel):
    master_key: str = Field(..., min_length=8)


class TestConnectionRequest(BaseModel):
    webdav_url: str = Field(..., min_length=1, max_length=500)
    webdav_username: str = Field(..., min_length=1, max_length=200)
    webdav_password: str = Field(..., min_length=1, max_length=500)


class AutoSyncRequest(BaseModel):
    enabled: bool


class ConflictResolveRequest(BaseModel):
    record_type: str = Field(..., description="表名: favorites/todos/skills/custom_sources/secrets")
    record_key: str = Field(..., description="记录主键")
    choice: str = Field(..., pattern="^(local|remote)$", description="选择保留哪一方")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _err_to_http(e: Exception) -> HTTPException:
    """统一错误 → HTTP 状态码。"""
    if isinstance(e, InvalidMasterKeyError):
        return HTTPException(status_code=401, detail={"message": "主密钥错误"})
    msg = str(e)
    if "不存在" in msg:
        return HTTPException(status_code=404, detail={"message": msg})
    if "未初始化" in msg or "未配置" in msg or "未解锁" in msg:
        return HTTPException(status_code=409, detail={"message": msg})
    if "WebDAV" in msg and ("失败" in msg or "认证" in msg):
        return HTTPException(status_code=502, detail={"message": msg})
    return HTTPException(status_code=400, detail={"message": msg})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/status")
async def get_status():
    """当前 sync_configs + status 摘要 + 最近 5 条历史。"""
    svc = SyncService()
    status = await asyncio.to_thread(svc.status)
    history = await asyncio.to_thread(svc.history, 5)
    return {
        "version": "1.0",
        "status": status,
        "recent_history": history,
    }


@router.post("/config", status_code=200)
async def upsert_config(req: UpsertConfigRequest):
    """upsert WebDAV 配置。master_key 始终必填 (验证身份 + 加密新密码)。

    P1.1: 业务逻辑下沉到 SyncConfigService, router 只做参数提取/响应构造。
    """
    svc = SyncConfigService()
    try:
        cfg_dict = svc.upsert_config(
            webdav_url=req.webdav_url,
            webdav_username=req.webdav_username,
            webdav_password=req.webdav_password,
            master_key=req.master_key,
            remote_path=req.remote_path,
            auto_sync_enabled=req.auto_sync_enabled,
            auto_sync_interval_minutes=req.auto_sync_interval_minutes,
            sync_frequency=req.sync_frequency,
        )
    except ValueError as e:
        msg = str(e)
        status = 409 if "未初始化" in msg or "首次配置" in msg else 401
        raise HTTPException(status_code=status, detail={"message": msg})
    return {"version": "1.0", "config": cfg_dict}


@router.delete("/config", status_code=200)
async def delete_config():
    """删除 sync 配置 (并清空 sync_states / history)。

    P1.1: 业务逻辑下沉到 SyncConfigService。
    """
    svc = SyncConfigService()
    try:
        deleted = svc.delete_config()
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"message": str(e)})
    # 记录 config id 已删除 (保留审计语义)
    return {"version": "1.0", "deleted": deleted, "id": None}


@router.post("/test", status_code=200)
async def test_connection(req: TestConnectionRequest):
    """用明文 webdav_url/username/password 测试连通性 (不落库)。"""
    client = WebDAVClient(req.webdav_url, req.webdav_username, req.webdav_password)
    ok, msg = await client.test_connection()
    return {
        "version": "1.0",
        "ok": ok,
        "message": msg,
    }


@router.post("/push", status_code=200)
async def manual_push(req: PushRequest):
    """手动 push: build → encrypt → WebDAV PUT。"""
    svc = SyncService()
    try:
        result = await svc.push(master_key=req.master_key)
    except Exception as e:
        raise _err_to_http(e)
    return {"version": "1.0", **result}


@router.post("/pull", status_code=200)
async def manual_pull(req: PullRequest):
    """手动 pull: GET → decrypt → 3-way merge → apply。"""
    svc = SyncService()
    try:
        result = await svc.pull(master_key=req.master_key)
    except Exception as e:
        raise _err_to_http(e)
    return {"version": "1.0", **result}


@router.post("/bidirectional", status_code=200)
async def manual_bidirectional(req: BidirectionalRequest):
    """手动双向: 拉远端 → 较新者赢。"""
    svc = SyncService()
    try:
        result = await svc.bidirectional(master_key=req.master_key)
    except Exception as e:
        raise _err_to_http(e)
    return {"version": "1.0", **result}


@router.get("/history")
async def list_history(limit: int = 50):
    """最近 N 条同步记录。"""
    cfg_repo = SyncConfigRepository()
    cfg = cfg_repo.get_default()
    if cfg is None:
        return {"version": "1.0", "history": []}
    history = SyncHistoryRepository().list_recent(cfg.id, limit=min(max(1, limit), 200))
    return {"version": "1.0", "history": history}


@router.post("/auto", status_code=200)
async def set_auto_sync(req: AutoSyncRequest):
    """开启/关闭自动同步 (只改 auto_sync_enabled, 不改 webdav 凭据)。

    P1.1: 业务逻辑下沉到 SyncConfigService。
    """
    svc = SyncConfigService()
    try:
        svc.set_auto_sync(enabled=req.enabled)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"message": str(e)})
    return {
        "version": "1.0",
        "auto_sync_enabled": req.enabled,
    }


@router.get("/bundle/preview")
async def preview_bundle():
    """预览本机 bundle (debug, 不含 secrets 密文)。

    用于 UI 上展示「即将同步的字段数」, 方便用户预演同步结果。
    """
    svc = SyncService()
    bundle = await asyncio.to_thread(svc.build_bundle)
    preview = {
        "version": bundle.get("version"),
        "device_id": bundle.get("device_id"),
        "merged_at": bundle.get("merged_at"),
        "record_counts": {
            k: len(v) if isinstance(v, list) else (len(v) if isinstance(v, dict) else 0)
            for k, v in bundle.get("records", {}).items()
        },
    }
    return {"version": "1.0", "preview": preview}


@router.get("/conflicts")
async def list_conflicts():
    """返回最近一次同步的冲突详情 (base/local/remote 三方值)。"""
    cfg_repo = SyncConfigRepository()
    cfg = cfg_repo.get_default()
    if cfg is None:
        return {"version": "1.0", "conflicts": [], "total": 0}
    history_repo = SyncHistoryRepository()
    recent = history_repo.list_recent(cfg.id, limit=1)
    if not recent:
        return {"version": "1.0", "conflicts": [], "total": 0}
    last = recent[0]
    table_conflicts_raw = last.get("table_conflicts")
    if not table_conflicts_raw:
        return {"version": "1.0", "conflicts": [], "total": 0}
    try:
        table_conflicts = json.loads(table_conflicts_raw) if isinstance(table_conflicts_raw, str) else table_conflicts_raw
    except Exception:
        return {"version": "1.0", "conflicts": [], "total": 0}
    total = sum(table_conflicts.values()) if isinstance(table_conflicts, dict) else 0
    return {
        "version": "1.0",
        "conflicts": table_conflicts,
        "total": total,
        "sync_id": last.get("id"),
        "direction": last.get("direction"),
        "started_at": last.get("started_at"),
    }


@router.post("/conflicts/resolve", status_code=200)
async def resolve_conflict(req: ConflictResolveRequest):
    """裁决单条冲突: 选择保留 local 或 remote。

    v1.3.0: 简化实现 — 记录裁决结果到 sync_states, 下次同步时应用。
    """
    cfg_repo = SyncConfigRepository()
    cfg = cfg_repo.get_default()
    if cfg is None:
        raise HTTPException(status_code=404, detail={"message": "sync config 不存在"})
    state_repo = SyncStateRepository()
    state = state_repo.get_by_config(cfg.id)
    if state is None:
        raise HTTPException(status_code=404, detail={"message": "无同步状态记录"})
    try:
        merged = json.loads(state.merged_bundle) if isinstance(state.merged_bundle, str) else state.merged_bundle
    except Exception:
        raise HTTPException(status_code=500, detail={"message": "无法解析 merged bundle"})
    records = merged.get("records", {})
    table_data = records.get(req.record_type)
    if table_data is None:
        raise HTTPException(status_code=404, detail={"message": f"表 {req.record_type} 不存在"})
    if isinstance(table_data, list):
        found = False
        for item in table_data:
            pk_map = {
                "favorites": "hotspot_id",
                "todos": lambda x: f"{x.get('source_type', '')}::{x.get('source_id', '')}",
                "skills": "name",
                "custom_sources": "url",
                "secrets": "name",
            }
            pk_fn = pk_map.get(req.record_type)
            if pk_fn is None:
                break
            key = pk_fn(item) if callable(pk_fn) else item.get(pk_fn)
            if key == req.record_key:
                item["_conflict_resolved"] = req.choice
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail={"message": f"记录 {req.record_key} 不存在"})
    state_repo.update_merged_bundle(cfg.id, json.dumps(merged, ensure_ascii=False))
    return {"version": "1.0", "resolved": True, "record_type": req.record_type, "record_key": req.record_key, "choice": req.choice}


class AutoResolveRequest(BaseModel):
    record_type: str = Field(..., description="表名")
    choice: str = Field(..., pattern="^(local|remote)$", description="保留哪一方")


@router.post("/conflicts/auto-resolve", status_code=200)
async def auto_resolve_conflicts(req: AutoResolveRequest):
    """批量裁决某表所有冲突（简化版，不逐条指定 record_key）。"""
    cfg_repo = SyncConfigRepository()
    cfg = cfg_repo.get_default()
    if cfg is None:
        raise HTTPException(status_code=404, detail={"message": "sync config 不存在"})
    state_repo = SyncStateRepository()
    state = state_repo.get_by_config(cfg.id)
    if state is None:
        raise HTTPException(status_code=404, detail={"message": "无同步状态记录"})
    try:
        merged = json.loads(state.merged_bundle) if isinstance(state.merged_bundle, str) else state.merged_bundle
    except Exception:
        raise HTTPException(status_code=500, detail={"message": "无法解析 merged bundle"})
    records = merged.get("records", {})
    table_data = records.get(req.record_type)
    if table_data is None:
        raise HTTPException(status_code=404, detail={"message": f"表 {req.record_type} 不存在"})
    pk_map = {
        "favorites": "hotspot_id",
        "todos": "source_id",
        "skills": "name",
        "custom_sources": "url",
        "secrets": "name",
    }
    count = 0
    if isinstance(table_data, list):
        for item in table_data:
            item["_conflict_resolved"] = req.choice
            count += 1
    state_repo.update_merged_bundle(cfg.id, json.dumps(merged, ensure_ascii=False))
    return {"version": "1.0", "resolved": True, "record_type": req.record_type, "choice": req.choice, "count": count}


__all__ = ["router"]

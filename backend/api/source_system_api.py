"""系统信源手动管理 API — 数据源治理 T2 (设计稿 §3.3)。

路由清单:
- ``GET    /api/sources/system``        注册层源列表 (media_kind/status/enabled/notes)
- ``DELETE /api/sources/system/{sid}``  物理删除 (reason 必填; 先审计后删 + 级联同名 source_stats)
- ``PATCH  /api/sources/system/{sid}``  启停 toggle (审计)

审计强制: 破坏性动作先写 source_cleanup_log (migration 122) 再动数据;
删除不带 reason → 422 拒绝。防呆 (active 源二次确认) 由前端负责,
后端不强拦但全部记审计 (owner 裁决 §2)。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.logging_config import logger
from backend.repository.source_cleanup_log_repo import SourceCleanupLogRepository
from backend.repository.source_scheduler_repo import SourceSchedulerRepository
from backend.repository.source_stats_repo import SourceStatsRepository

router = APIRouter(prefix="/api/sources", tags=["sources"])

# GET /system 返回的字段白名单 (供前端矩阵; list_all 返回 SELECT * 全列)
_SYSTEM_SOURCE_FIELDS = (
    "id", "category", "name", "kind", "url", "feed_url",
    "enabled", "status", "media_kind", "notes", "last_fetch_at",
)


class SystemSourcePatchRequest(BaseModel):
    enabled: bool


def _audit(source_ident: str, reason: str, executed_by: str) -> None:
    """审计落点 (先于任何 DELETE/UPDATE 调用)。"""
    SourceCleanupLogRepository().add(
        source_layer="crawler_sources",
        source_ident=source_ident,
        reason=reason,
        executed_by=executed_by,
    )


@router.get("/system")
async def list_system_sources():
    """列出注册层 (crawler_sources) 全部源, 供前端矩阵/管理面消费。"""
    rows = SourceSchedulerRepository().list_all()
    return {
        "sources": [
            {k: r.get(k) for k in _SYSTEM_SOURCE_FIELDS if k in r}
            for r in rows
        ],
    }


@router.delete("/system/{sid}")
async def delete_system_source(sid: str, reason: str = Query(min_length=1)):
    """删除系统源: 必带 reason → 审计 → 删注册行 + 级联删同类目统计行。

    级联按 (name, category) 限定: 同名跨类目的其他统计行仍在供给,
    不得连带归零 (治理 T2 review fix)。
    """
    repo = SourceSchedulerRepository()
    row = repo.get_by_id(sid)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"system source id={sid} not found"},
        )
    ident = str(row.get("name") or sid)
    category = str(row.get("category") or "") or None
    # 审计强制: 先写 log (reason 缺失由 FastAPI 422 拦截, 到不了这里)
    _audit(ident, reason, executed_by="owner")
    repo.delete(sid)
    name = str(row.get("name") or "")
    stats_deleted = (
        SourceStatsRepository().delete_by_source_name(name, category=category)
        if name
        else 0
    )
    logger.info(
        f"system_source deleted: id={sid} ident={ident} category={category} "
        f"reason={reason} stats_rows_deleted={stats_deleted}"
    )
    return {
        "status": "ok",
        "deleted": sid,
        "ident": ident,
        "category": category,
        "stats_rows_deleted": stats_deleted,
    }


@router.patch("/system/{sid}")
async def toggle_system_source(sid: str, req: SystemSourcePatchRequest):
    """启停系统源 (toggle enabled), 先审计后动数据。"""
    repo = SourceSchedulerRepository()
    row = repo.get_by_id(sid)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"system source id={sid} not found"},
        )
    ident = str(row.get("name") or sid)
    # 审计强制: 先写 log 再 UPDATE (与本文件头约定一致)
    _audit(ident, f"toggle_enabled={str(req.enabled).lower()}", executed_by="owner")
    ok = repo.update_health_state(sid, enabled=1 if req.enabled else 0)
    if not ok:
        raise HTTPException(
            status_code=500,
            detail={"message": f"toggle failed for id={sid}"},
        )
    logger.info(f"system_source toggled: id={sid} enabled={req.enabled}")
    return {"status": "ok", "id": sid, "enabled": req.enabled}

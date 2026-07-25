"""v1.8 Phase 8 — 追抓资讯 API.

端点
----
- ``POST /api/catchup/run``    手动触发追抓 (manual mode)
- ``GET  /api/catchup/status`` 当前/历史 run 状态
- ``POST /api/catchup/abort``  中止当前 manual run
- ``POST /api/catchup/auto``   watchdog 等内部用 (auto mode, 无并发锁)

设计
----
- manual 受 ``_lock + _current_manual_run`` 约束 (返回 409 if busy)
- auto 模式不阻塞 manual, 优先级低
- 状态从 ``catchup_runs`` 表读, 实时反映后台进度
- abort 协作式: 标 DB 状态为 aborted, _execute 在下一个写库点会终止

错误码
------
- 200 成功
- 202 接受 (manual 触发, 异步执行)
- 400 参数错误 (since 缺失 / mode 错)
- 404 run_id 不存在
- 409 manual 冲突 (已有 manual 在跑)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from backend.logging_config import logger
from backend.repository.catchup_repo import CatchupRepository
from backend.services import catchup_service

router = APIRouter(prefix="/api/catchup", tags=["catchup"])
_logger = logger.bind(component="api.catchup")
_repo = CatchupRepository()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class CatchupRunRequest(BaseModel):
    """POST /api/catchup/run 的请求体.

    字段
    ----
    - since: 必填, ISO 8601
    - until: 可选, 默认 now
    - categories: 可选, 空 = all 7 分类
    - max_per_source: 可选, 默认 20, 范围 1-200
    """

    since: str = Field(..., description="追抓窗口起点 (ISO 8601 UTC)")
    until: Optional[str] = Field(None, description="追抓窗口终点, 默认 now")
    categories: list[str] = Field(
        default_factory=list,
        description="要追抓的分类 list, 空=全部",
    )
    max_per_source: int = Field(
        default=20,
        ge=1,
        le=200,
        description="单源最大抓取数 (节流)",
    )

    @field_validator("since")
    @classmethod
    def _validate_since(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError(f"invalid since ISO 8601: {e}")
        return v

    @field_validator("until")
    @classmethod
    def _validate_until(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError(f"invalid until ISO 8601: {e}")
        return v


class CatchupRunResponse(BaseModel):
    """POST /api/catchup/run 的响应 (触发后立即返回)."""

    run_id: int
    status: str
    mode: str
    since: str
    until: Optional[str]
    categories: list[str]
    max_per_source: int
    started_at: str
    message: str = "catchup enqueued"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_to_dict(run) -> dict[str, Any]:
    """CatchupRun -> API dict (datetime 序列化友好)."""
    if run is None:
        return None
    return run.to_dict()


# ---------------------------------------------------------------------------
# POST /api/catchup/run — manual 触发
# ---------------------------------------------------------------------------
@router.post("/run", response_model=CatchupRunResponse, status_code=202)
async def post_catchup_run(req: CatchupRunRequest) -> CatchupRunResponse:
    """手动触发一次追抓 (manual mode).

    返回 202 (Accepted) + run_id, 后台异步执行.
    已有 manual 在跑时返回 409 Conflict.
    """
    try:
        run_id = await catchup_service.enqueue_catchup(
            mode="manual",
            since=req.since,
            until=req.until,
            categories=list(req.categories),
            max_per_source=int(req.max_per_source),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"message": f"invalid parameters: {e}"},
        )

    run = _repo.get(run_id)
    if run is None:
        # 极小概率: enqueue 成功但 read 不到, 返回 500
        raise HTTPException(
            status_code=500,
            detail={"message": f"run_id={run_id} created but not retrievable"},
        )

    return CatchupRunResponse(
        run_id=run.id,
        status=run.status,
        mode=run.mode,
        since=run.since_window,
        until=run.until_window,
        categories=run.categories,
        max_per_source=run.max_per_source,
        started_at=run.started_at,
    )


# ---------------------------------------------------------------------------
# GET /api/catchup/status — 当前/历史 run
# ---------------------------------------------------------------------------
@router.get("/status")
async def get_catchup_status(
    limit: int = Query(7, ge=1, le=50, description="返回最近 N 条"),
    include_running: bool = Query(True, description="包含 running 行"),
) -> dict[str, Any]:
    """返回当前 manual run + 最近 N 条历史.

    字段
    ----
    - current_running: 当前 running 状态的 run (manual 或 auto, 最近一条)
    - current_manual_run_id: 当前 manual run id (用于 abort)
    - recent: 最近 N 条 (按 started_at DESC)
    - last_orphan_recovery_at: watchdog 最近恢复时间戳
    """
    current_running = _repo.get_current_running()
    recent = _repo.list_recent(limit=limit)
    return {
        "current_running": _run_to_dict(current_running) if current_running else None,
        "current_manual_run_id": catchup_service.get_current_manual_run_id(),
        "recent": [_run_to_dict(r) for r in recent],
        "last_orphan_recovery_at": catchup_service.get_last_orphan_recovery_at(),
        "total_recent": len(recent),
    }


# ---------------------------------------------------------------------------
# POST /api/catchup/abort — 中止当前 manual
# ---------------------------------------------------------------------------
class AbortRequest(BaseModel):
    run_id: Optional[int] = Field(
        None,
        description="可选: 指定 run_id, 不传则中止当前 manual",
    )


@router.post("/abort")
async def post_catchup_abort(req: AbortRequest = AbortRequest()) -> dict[str, Any]:
    """中止一个 running 状态的 run.

    - 不传 run_id: 中止当前 manual (若有)
    - 传 run_id: 中止指定 run (仅当 status='running')
    """
    target_id: Optional[int] = None
    if req.run_id is not None:
        # 校验 run_id 存在
        run = _repo.get(int(req.run_id))
        if run is None:
            raise HTTPException(
                status_code=404,
                detail={"message": f"run_id={req.run_id} not found"},
            )
        if run.status != "running":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"run_id={req.run_id} is not running (status={run.status})",
                    "status": run.status,
                },
            )
        if not _repo.abort(int(req.run_id)):
            raise HTTPException(
                status_code=409,
                detail={"message": f"run_id={req.run_id} abort failed (race)"},
            )
        target_id = int(req.run_id)
        # 同步释放 module state
        if catchup_service.get_current_manual_run_id() == target_id:
            from backend.services.catchup_service import _current_manual_run
            import backend.services.catchup_service as cs
            cs._current_manual_run = None
        _logger.info(f"abort: run_id={target_id} marked aborted by user request")
    else:
        # 中止当前 manual
        target_id = await catchup_service.abort_current()
        if target_id is None:
            return {
                "ok": False,
                "message": "no manual run in progress",
                "aborted_run_id": None,
            }
        _logger.info(f"abort: current manual run_id={target_id} aborted")

    return {
        "ok": True,
        "aborted_run_id": target_id,
        "message": f"run_id={target_id} marked aborted",
    }


# ---------------------------------------------------------------------------
# POST /api/catchup/auto — 内部用 (auto mode)
# ---------------------------------------------------------------------------
class AutoRequest(BaseModel):
    since: str
    until: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    max_per_source: int = Field(default=20, ge=1, le=200)


@router.post("/auto", response_model=CatchupRunResponse, status_code=202)
async def post_catchup_auto(req: AutoRequest) -> CatchupRunResponse:
    """内部 / watchdog 触发的追抓 (auto mode).

    与 manual 区别: auto 不阻塞 manual, 优先级低, 防抖逻辑走
    ``catchup_service.should_enqueue_auto()``.
    """
    try:
        run_id = await catchup_service.enqueue_catchup(
            mode="auto",
            since=req.since,
            until=req.until,
            categories=list(req.categories),
            max_per_source=int(req.max_per_source),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"message": f"invalid parameters: {e}"},
        )

    run = _repo.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=500,
            detail={"message": f"auto run_id={run_id} not retrievable"},
        )
    return CatchupRunResponse(
        run_id=run.id,
        status=run.status,
        mode=run.mode,
        since=run.since_window,
        until=run.until_window,
        categories=run.categories,
        max_per_source=run.max_per_source,
        started_at=run.started_at,
    )


# ---------------------------------------------------------------------------
# GET /api/catchup/runs/{run_id} — 单条 run 详情 (调试用)
# ---------------------------------------------------------------------------
@router.get("/runs/{run_id}")
async def get_catchup_run(run_id: int) -> dict[str, Any]:
    """返回单条 run 详情."""
    run = _repo.get(int(run_id))
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"run_id={run_id} not found"},
        )
    return _run_to_dict(run)


__all__ = ["router"]

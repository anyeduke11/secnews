"""v1.0 T12 Action API (contracts §6 + §0.4).

路由清单 (前缀 /api/v1/actions)
--------
- ``POST /api/v1/actions/generate``       dsh 调 inspection-materials (拆分至 action_generate_api)
- ``GET  /api/v1/actions``                列表 (query: case_id 必填 + status/judgment_id/limit/offset)
- ``GET  /api/v1/actions/{id}``           详情
- ``POST /api/v1/actions/{id}/approve``   planned → approved (CAS expected_revision)
- ``POST /api/v1/actions/{id}/start``     approved → running (CAS + 创建 Run)
- ``POST /api/v1/actions/{id}/cancel``    任何非终态 → cancelled
- ``POST /api/v1/actions/{id}/finish``    v0.8.9 C1-2 (拆分至 action_finish_api, 聚合注册)
- ``POST /api/v1/actions/{id}/finish``    v0.8.9 C1-2: running → succeeded/failed (须名下 run 全终态)

错误
----
- ``E_VALIDATION`` (400) — 字段校验 / dsh 解析失败 / judgment 未 published
- ``E_NOT_FOUND``  (404) — id 不存在
- ``E_CONFLICT``   (409) — revision 不匹配 (CAS) / 状态不允许当前动作
- 响应一律包含 allowed_actions + revision + reason (contracts §0.3)
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.action_service import (
    ActionConflictError,
    ActionNotFoundError,
    ActionService,
    ActionValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/actions", tags=["v1-actions"])


# ---------------------------------------------------------------------------
# Request / Response 模型
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------
def _list(
    case_id: str, status: str | None, judgment_id: str | None, limit: int, offset: int,
) -> dict[str, Any]:
    svc = ActionService()
    result = svc.list_by_case(
        case_id, status=status, judgment_id=judgment_id, limit=limit, offset=offset,
    )
    return _list_response(result["items"], total=result["total"])


def _get(action_id: str) -> dict[str, Any]:
    svc = ActionService()
    try:
        a = svc.get(action_id)
    except ActionNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    return {"version": API_VERSION, "item": _action_to_dict(a)}


class StateChangeRequest(BaseModel):
    """POST /api/v1/actions/{id}/{approve|start|cancel} — body 必含 expected_revision."""

    expected_revision: int = Field(ge=1)


class StartActionRequest(StateChangeRequest):
    """start 额外需要 idempotency_key + protocol.

    v1.0 C07 R05 修复: protocol 必填 (旧 default='mock' 让默认路径虚报完成).
    pattern 限制生产协议 {dsh, pi, direct}, 不再含 'mock' (mock 走 skill_runner 演示模式).
    """

    idempotency_key: str = Field(min_length=1, max_length=200)
    protocol: str = Field(pattern="^(dsh|pi|direct)$")
    trigger_source: str = Field(default="user", pattern="^(user|agent|system|scheduled|webhook)$")
    skill_id: str | None = None


def _approve(action_id: str, req: StateChangeRequest) -> dict[str, Any]:
    svc = ActionService()
    try:
        a = svc.approve(action_id, expected_revision=req.expected_revision, approved_by="user")
    except ActionNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except ActionConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    except ActionValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    return {"version": API_VERSION, "item": _action_to_dict(a)}


def _start(action_id: str, req: StartActionRequest) -> dict[str, Any]:
    svc = ActionService()
    try:
        out = svc.start(
            action_id, expected_revision=req.expected_revision,
            idempotency_key=req.idempotency_key, protocol=req.protocol,
            trigger_source=req.trigger_source, skill_id=req.skill_id,
        )
    except ActionNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except ActionConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    except ActionValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    return {
        "version": API_VERSION,
        "item": _action_to_dict(out["action"]),
        "run": out["run"],
        "replayed": out["replayed"],
    }


def _cancel(action_id: str, req: StateChangeRequest) -> dict[str, Any]:
    svc = ActionService()
    try:
        a = svc.cancel(action_id, expected_revision=req.expected_revision, reason="user cancel")
    except ActionNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except ActionConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    return {"version": API_VERSION, "item": _action_to_dict(a)}


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@router.get("", response_model=None)
async def list_actions(
    case_id: str = Query(..., min_length=1, max_length=26),
    status: str | None = Query(None),
    judgment_id: str | None = Query(None, max_length=26),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return await asyncio.to_thread(_list, case_id, status, judgment_id, limit, offset)


@router.get("/{action_id}", response_model=None)
async def get_action(action_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_get, action_id)


@router.post("/{action_id}/approve", response_model=None)
async def approve_action(
    action_id: str, req: StateChangeRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_approve, action_id, req)


@router.post("/{action_id}/start", response_model=None)
async def start_action(
    action_id: str, req: StartActionRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_start, action_id, req)


@router.post("/{action_id}/cancel", response_model=None)
async def cancel_action(
    action_id: str, req: StateChangeRequest = Body(...)
) -> dict[str, Any]:
    return await asyncio.to_thread(_cancel, action_id, req)

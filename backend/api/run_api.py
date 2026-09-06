"""v1.0 T12 Run API (contracts §7 + §0.4) — 列表 + 详情 (创建走 action.start 端点)."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.services.run_service import (
    RunConflictError,
    RunNotFoundError,
    RunService,
    RunValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/runs", tags=["v1-runs"])


def _run_to_dict(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"],
        "action_id": r["action_id"],
        "attempt": r["attempt"],
        "skill_id": r.get("skill_id"),
        "protocol": r["protocol"],
        "trigger_source": r["trigger_source"],
        "idempotency_key": r["idempotency_key"],
        "status": r["status"],
        "inputs": r.get("inputs", {}),
        "steps": r.get("steps", []),
        "budget_tokens": r.get("budget_tokens"),
        "budget_seconds": r.get("budget_seconds"),
        "started_at": r.get("started_at"),
        "finished_at": r.get("finished_at"),
        "duration_ms": r.get("duration_ms"),
        "result_excerpt": r.get("result_excerpt"),
        "error": r.get("error"),
        "artifact_ids": r.get("artifact_ids", []),
        "revision": r["revision"],
        "allowed_actions": r.get("allowed_actions", []),
        "reason": r.get("reason"),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


def _list_response(items: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {
        "version": API_VERSION,
        "items": [_run_to_dict(r) for r in items],
        "total": total if total is not None else len(items),
    }


def _list(action_id: str, status: str | None, limit: int, offset: int) -> dict[str, Any]:
    svc = RunService()
    result = svc.list_by_action(action_id, status=status, limit=limit, offset=offset)
    return _list_response(result["items"], total=result["total"])


def _get(run_id: str) -> dict[str, Any]:
    svc = RunService()
    try:
        r = svc.get(run_id)
    except RunNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    return {"version": API_VERSION, "item": _run_to_dict(r)}


@router.get("", response_model=None)
async def list_runs(
    action_id: str = Query(..., min_length=1, max_length=40),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return await asyncio.to_thread(_list, action_id, status, limit, offset)


@router.get("/{run_id}", response_model=None)
async def get_run(run_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_get, run_id)

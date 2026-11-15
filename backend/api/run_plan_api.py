"""run_plan_api.py — v0.8.9 P3 C3-4 ExecutionPlan 审批端点 (L1 计划层)。

路由 (prefix /api/v1/runs — 与 run_api 同前缀不同路径, 无冲突):
- GET  /api/v1/runs/{id}/plan            读 plan 信封 (无 → 404)
- POST /api/v1/runs/{id}/plan            提交草稿 (manual 表单 或 ai_draft 结果)
- POST /api/v1/runs/{id}/plan/generate   ai_hub 起草 → draft (失败 503 → 人工手写兜底)
- POST /api/v1/runs/{id}/plan/approve    draft → approved (冻结 immutable; 默认拒绝语义的显式放行)
- POST /api/v1/runs/{id}/plan/reject     draft → rejected (reason 必填)

错误码位: 404 E_NOT_FOUND / 409 E_CONFLICT / 400 E_VALIDATION / 503 E_SOURCE_UNAVAILABLE (LLM)。
状态机与不变量见 backend/services/execution_plan/service.py (L1 默认拒绝 / approved immutable / L4 hash)。
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from backend.services.execution_plan.generator import ExecutionPlanGenerationError
from backend.services.execution_plan.service import (
    ExecutionPlanConflictError,
    ExecutionPlanNotFoundError,
    ExecutionPlanService,
    ExecutionPlanValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/runs", tags=["v1-runs"])


class PlanSubmitBody(BaseModel):
    """提交 ExecutionPlan 草稿 (manual 表单 或 ai_draft 回传修订)。"""

    plan: dict[str, Any]
    submitted_by: str = Field(default="user", max_length=200)
    source: str = Field(default="manual", pattern="^(manual|ai_draft)$")


class PlanReviewBody(BaseModel):
    reviewed_by: str = Field(default="user", max_length=200)


class PlanRejectBody(PlanReviewBody):
    # 业务必填 (空/超长由 service 返回 400), 不在 Pydantic 层挡成 422 (run_ledger RejectBody 同款)
    reason: str = Field(default="", max_length=200)


class PlanGenerateBody(BaseModel):
    action_id: str = Field(min_length=1, max_length=40)
    submitted_by: str = Field(default="user", max_length=200)


_PLAN_ERRORS = (
    ExecutionPlanNotFoundError,
    ExecutionPlanConflictError,
    ExecutionPlanValidationError,
)


def _svc() -> ExecutionPlanService:
    return ExecutionPlanService()


def _map_plan_errors(e: Exception) -> HTTPException:
    status, code = 400, "E_VALIDATION"
    if isinstance(e, ExecutionPlanNotFoundError):
        status, code = 404, "E_NOT_FOUND"
    elif isinstance(e, ExecutionPlanConflictError):
        status, code = 409, "E_CONFLICT"
    return HTTPException(status_code=status, detail={"code": code, "message": str(e)})


def _call(fn: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """统一 {version, item} 信封 + E_* 错误码 (与 run_api / run_ledger 同族)。"""
    try:
        env = fn(*args, **kwargs)
    except _PLAN_ERRORS as e:
        raise _map_plan_errors(e)
    return {"version": API_VERSION, "item": env}


def _generate(run_id: str, body: PlanGenerateBody) -> dict[str, Any]:
    from backend.services.action_service import (
        ActionNotFoundError,
        ActionService,
    )
    from backend.services.execution_plan.generator import generate_plan_draft

    try:
        action = ActionService().get(body.action_id)
    except ActionNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    try:
        env = generate_plan_draft(
            run_id=run_id, action=action, submitted_by=body.submitted_by,
        )
    except ExecutionPlanGenerationError as e:
        # LLM 不可用/输出非法 → 503 (人工手写兜底, D3 裁决③)
        raise HTTPException(
            status_code=503,
            detail={"code": "E_SOURCE_UNAVAILABLE", "message": str(e),
                    "fallback": "manual_form"},
        )
    except _PLAN_ERRORS as e:
        raise _map_plan_errors(e)
    return {"version": API_VERSION, "item": env}


@router.get("/{run_id}/plan", response_model=None)
async def get_run_plan(run_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_call, _svc().get, run_id)


@router.post("/{run_id}/plan", response_model=None)
async def submit_run_plan(run_id: str, body: PlanSubmitBody = Body(...)) -> dict[str, Any]:
    return await asyncio.to_thread(
        _call, _svc().submit, run_id, body.plan,
        submitted_by=body.submitted_by, source=body.source,
    )


@router.post("/{run_id}/plan/generate", response_model=None)
async def generate_run_plan(run_id: str, body: PlanGenerateBody = Body(...)) -> dict[str, Any]:
    """ai_hub 起草建议 plan → draft (L1: 未审批不执行; 失败 503 落人工兜底)."""
    return await asyncio.to_thread(_generate, run_id, body)


@router.post("/{run_id}/plan/approve", response_model=None)
async def approve_run_plan(run_id: str, body: PlanReviewBody = Body(...)) -> dict[str, Any]:
    return await asyncio.to_thread(
        _call, _svc().approve, run_id, reviewed_by=body.reviewed_by,
    )


@router.post("/{run_id}/plan/reject", response_model=None)
async def reject_run_plan(run_id: str, body: PlanRejectBody = Body(...)) -> dict[str, Any]:
    return await asyncio.to_thread(
        _call, _svc().reject, run_id,
        reviewed_by=body.reviewed_by, reason=body.reason,
    )

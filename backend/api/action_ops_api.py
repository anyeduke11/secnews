"""action_ops_api.py — v0.8.9 P1 拆分: Action generate + finish 端点 (自 action_api.py 迁出).

拆分原因: action_api 为 236 行豁免文件, 守卫只许收缩 (拆分连锁先例 D5)。
注册: _registry_extensions 直挂本 router (FastAPI 0.139 嵌套惰性聚合不可用,
两层 _IncludedRouter 嵌套致路由 404 — 实测 2026-11-14); routers 97→98 / core_routers 65→66。

路由:
- POST /api/v1/actions/generate        dsh 调 inspection-materials (GenerateActionRequest)
- POST /api/v1/actions/{id}/finish     running → succeeded/failed (FinishActionRequest)

守卫 (R-1 一致性): finish 须名下所有 run 已终态; finish(succeeded) 须 ≥1 succeeded run (RA-9)。
_action_to_dict 经函数级惰性 import (防 action_api ↔ 本文件模块级环)。
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from backend.services.action_service import (
    ActionConflictError,
    ActionNotFoundError,
    ActionService,
    ActionValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/actions", tags=["v1-actions"])


class GenerateActionRequest(BaseModel):
    """POST /api/v1/actions/generate — dsh 调 inspection-materials."""

    case_id: str = Field(min_length=1, max_length=26)
    judgment_id: str = Field(min_length=1, max_length=26)
    title: str = Field(min_length=1, max_length=200)
    subject_name: str = Field(min_length=1, max_length=200)
    cve_id: str = Field(min_length=1, max_length=64)
    scope: str = Field(default="", max_length=2000)
    evidence_materials: list[dict[str, Any]] = Field(default_factory=list)


class FinishActionRequest(BaseModel):
    """POST /api/v1/actions/{id}/finish — v0.8.9 C1-2 收口 (running → succeeded/failed)."""

    expected_revision: int = Field(ge=1)
    succeeded: bool
    reason: str | None = Field(default=None, max_length=500)


@router.post("/generate", response_model=None)
async def generate_action(req: GenerateActionRequest = Body(...)) -> dict[str, Any]:
    """dsh 调 inspection-materials 落 planned action (vendor 不可用时降 ai_hub)."""
    svc = ActionService()
    try:
        result = svc.create_with_dsh(
            case_id=req.case_id, judgment_id=req.judgment_id, title=req.title,
            subject_name=req.subject_name, cve_id=req.cve_id, scope=req.scope,
            evidence_materials=req.evidence_materials, submitted_by=req.submitted_by,
        )
    except ActionValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    except ActionConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    from backend.api.action_api import _action_to_dict  # 惰性 import 防模块级环
    return {
        "version": API_VERSION,
        "item": _action_to_dict(result["action"]),
        "idempotent_replay": result["idempotent_replay"],
    }


@router.post("/{action_id}/finish", response_model=None)
async def finish_action(
    action_id: str, req: FinishActionRequest = Body(...)
) -> dict[str, Any]:
    """v0.8.9 C1-2: running → succeeded/failed 收口 (须名下 run 全终态, RA-9)."""
    svc = ActionService()
    try:
        a = svc.finish(
            action_id, expected_revision=req.expected_revision, succeeded=req.succeeded,
        )
    except ActionNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except ActionConflictError as e:
        raise HTTPException(status_code=409, detail={"code": "E_CONFLICT", "message": str(e)})
    except ActionValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    from backend.api.action_api import _action_to_dict  # 惰性 import 防模块级环
    return {"version": API_VERSION, "item": _action_to_dict(a)}

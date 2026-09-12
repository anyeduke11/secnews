"""v1.0 T08 Case API (contracts §4 + §0.4 + §4.5).

路由清单 (前缀 /api/v1/cases)
--------
- ``POST   /api/v1/cases``          创建 — body: title/question/goal/scope/priority/...
- ``GET    /api/v1/cases``          列表 — query: status / priority / owner_role / subject_id / limit / offset
- ``GET    /api/v1/cases/{id}``     详情
- ``PATCH  /api/v1/cases/{id}``     CAS 更新 — body 必须含 expected_revision
- ``POST   /api/v1/cases/{id}/close`` 关闭 — body 必须含 expected_revision

错误
----
- ``E_VALIDATION`` (400) — 字段校验失败 / Pydantic 错误
- ``E_NOT_FOUND``  (404) — id 不存在
- ``E_CONFLICT``   (409) — revision 不匹配 (CAS) / 幂等键冲突 / 业务约束 (close 时有 active run)
- 响应一律包含 allowed_actions + revision + reason (contracts §0.3)

所有同步 DB 操作放 ``asyncio.to_thread`` (与 Phase 4 既有 API 一致)。
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from backend.logging_config import logger
from backend.services.case_service import (
    CaseConflictError,
    CaseNotFoundError,
    CaseService,
    CaseValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/cases", tags=["v1-cases"])


# ---------------------------------------------------------------------------
# Request / Response 模型
# ---------------------------------------------------------------------------
class CreateCaseRequest(BaseModel):
    """POST /api/v1/cases body — 必填 title + question, 其它可选."""

    title: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=500)
    goal: str | None = None
    scope: str | None = None
    priority: str = Field(default="p2", pattern="^(p0|p1|p2|p3)$")
    due_at: str | None = None
    subject_id: str | None = None
    owner_role: str = Field(default="user", pattern="^(user|system|shared)$")
    tags: list[str] = Field(default_factory=list)
    related_subject_ids: list[str] = Field(default_factory=list)
    related_signal_ids: list[str] = Field(default_factory=list)
    related_case_ids: list[str] = Field(default_factory=list)
    source: str = Field(default="manual", description="提交方标识 (manual|agent|system)")


class UpdateCaseRequest(BaseModel):
    """PATCH /api/v1/cases/{id} body — 必填 expected_revision (CAS)."""

    expected_revision: int = Field(ge=1)
    status: str | None = Field(default=None, pattern="^(open|in_progress|blocked|closed|archived)$")
    title: str | None = Field(default=None, max_length=120)
    question: str | None = Field(default=None, max_length=500)
    goal: str | None = None
    scope: str | None = None
    priority: str | None = Field(default=None, pattern="^(p0|p1|p2|p3)$")
    due_at: str | None = None
    tags: list[str] | None = None
    related_subject_ids: list[str] | None = None
    related_signal_ids: list[str] | None = None
    related_case_ids: list[str] | None = None
    reason: str | None = None


class CloseCaseRequest(BaseModel):
    """POST /api/v1/cases/{id}/close body."""

    expected_revision: int = Field(ge=1)


# ---------------------------------------------------------------------------
# 同步 helper (放线程池)
# ---------------------------------------------------------------------------
def _case_to_dict(case) -> dict[str, Any]:
    """Pydantic Case → JSON dict (datetime ISO)."""
    return case.model_dump(mode="json")


def _list_response(items: list, total: int | None = None) -> dict[str, Any]:
    return {
        "version": API_VERSION,
        "items": [_case_to_dict(c) for c in items],
        "total": total if total is not None else len(items),
    }


def _create(req: CreateCaseRequest) -> dict[str, Any]:
    svc = CaseService()
    try:
        case = svc.create_case(
            title=req.title,
            question=req.question,
            goal=req.goal,
            scope=req.scope,
            priority=req.priority,
            due_at=req.due_at,
            subject_id=req.subject_id,
            owner_role=req.owner_role,
            tags=req.tags,
            related_subject_ids=req.related_subject_ids,
            related_signal_ids=req.related_signal_ids,
            related_case_ids=req.related_case_ids,
            source=req.source,
        )
    except CaseValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    except CaseConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "E_CONFLICT",
                "message": str(e),
                "current_revision": e.current_revision,
                "current_status": e.current_status,
            },
        )
    return {"version": API_VERSION, "item": _case_to_dict(case)}


def _list(
    status: list[str] | None,
    priority: list[str] | None,
    owner_role: str | None,
    subject_id: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    svc = CaseService()
    items = svc.list_cases(
        status=status,
        priority=priority,
        owner_role=owner_role,
        subject_id=subject_id,
        limit=limit,
        offset=offset,
    )
    return _list_response(items)


def _get(case_id: str) -> dict[str, Any]:
    svc = CaseService()
    try:
        case = svc.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "E_NOT_FOUND", "message": str(e)},
        )
    return {"version": API_VERSION, "item": _case_to_dict(case)}


def _update(case_id: str, req: UpdateCaseRequest) -> dict[str, Any]:
    svc = CaseService()
    try:
        case = svc.update_case(
            case_id,
            expected_revision=req.expected_revision,
            status=req.status,
            title=req.title,
            question=req.question,
            goal=req.goal,
            scope=req.scope,
            priority=req.priority,
            due_at=req.due_at,
            tags=req.tags,
            related_subject_ids=req.related_subject_ids,
            related_signal_ids=req.related_signal_ids,
            related_case_ids=req.related_case_ids,
            reason=req.reason,
        )
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "E_NOT_FOUND", "message": str(e)},
        )
    except CaseConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "E_CONFLICT",
                "message": str(e),
                "current_revision": e.current_revision,
                "current_status": e.current_status,
            },
        )
    except CaseValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "E_VALIDATION", "message": str(e)},
        )
    return {"version": API_VERSION, "item": _case_to_dict(case)}


def _close(case_id: str, req: CloseCaseRequest) -> dict[str, Any]:
    svc = CaseService()
    try:
        case = svc.close_case(case_id, expected_revision=req.expected_revision)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "E_NOT_FOUND", "message": str(e)},
        )
    except CaseConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "E_CONFLICT",
                "message": str(e),
                "current_revision": e.current_revision,
                "current_status": e.current_status,
            },
        )
    return {"version": API_VERSION, "item": _case_to_dict(case)}


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@router.post("", status_code=201)
async def create_case_endpoint(req: CreateCaseRequest = Body(...)):
    """创建 Case — 走 V1EvidenceService.create_intent + commit_intent."""
    try:
        return await asyncio.to_thread(_create, req)
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover — 兜底
        logger.exception(f"create_case unhandled: {e}")
        raise HTTPException(
            status_code=500,
            detail={"code": "E_INTERNAL", "message": str(e)},
        )


# ---------------------------------------------------------------------------
# C11 R19: 聚合端点 — 单次拉齐 case + judgments + actions + runs + artifacts
# ---------------------------------------------------------------------------
def _aggregate(
    case_id: str,
    *,
    judgments_limit: int,
    actions_limit: int,
    runs_per_action: int,
    artifacts_per_run: int,
) -> dict[str, Any]:
    """C11 R19: Case 聚合查询, 避免前端 N+1.

    调用 1 次: case + judgments + actions + runs (per action) + artifacts (per run).
    旧实现 (前端): 1+1+1+N+N×M 个 HTTP 请求; 修复后: 1 个聚合端点.
    v0.8.5 证据/复利只读 SQL 在 v1_evidence_service / knowledge_service
    (Batch 2 D 下沉); 本函数只做聚合编排。
    """
    def _recall_candidates(case_dict: dict[str, Any]) -> list[dict[str, Any]]:
        """v0.8.5 D3 (SK-05 自动召回): 已发布知识 × case 文本匹配, 失败显空不阻断."""
        try:
            from backend.services.knowledge_service import auto_recall_for_case
            return auto_recall_for_case(case_dict)
        except Exception:
            return []

    from backend.services.action_service import ActionService
    from backend.services.artifact_service import ArtifactService
    from backend.services.judgment_service import JudgmentService
    from backend.services.knowledge_service import KnowledgeService
    from backend.services.run_service import RunService
    from backend.services.v1_evidence_service import V1EvidenceService

    c_svc = CaseService()
    try:
        case = c_svc.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail={"code": "E_NOT_FOUND", "message": str(e)},
        )

    j_svc = JudgmentService()
    judgments_resp = j_svc.list_by_case(case_id, limit=judgments_limit, offset=0)
    judgments = judgments_resp.get("items", []) if isinstance(judgments_resp, dict) else list(judgments_resp)

    a_svc = ActionService(dsh_caller=lambda _p: "{}")
    actions_resp = a_svc.list_by_case(case_id, limit=actions_limit, offset=0)
    actions = actions_resp.get("items", []) if isinstance(actions_resp, dict) else list(actions_resp)

    r_svc = RunService()
    art_svc = ArtifactService()
    runs: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    for a in actions:
        a_id = a.get("id") if isinstance(a, dict) else getattr(a, "id", None)
        if not a_id:
            continue
        try:
            run_resp = r_svc.list_by_action(a_id, limit=runs_per_action, offset=0)
            run_items = run_resp.get("items", []) if isinstance(run_resp, dict) else list(run_resp)
        except Exception:
            run_items = []
        runs.extend(run_items)
        for r in run_items:
            r_id = r.get("id") if isinstance(r, dict) else getattr(r, "id", None)
            if not r_id:
                continue
            try:
                art_resp = art_svc.list_by_run(r_id, limit=artifacts_per_run, offset=0)
                art_items = art_resp.get("items", []) if isinstance(art_resp, dict) else list(art_resp)
            except Exception:
                art_items = []
            artifacts.extend(art_items)

    return {
        "version": API_VERSION,
        "case": _case_to_dict(case),
        "evidence_materials": V1EvidenceService().case_evidence_materials(case_id),
        # v0.8.5 D3 (SK-05 自动召回): 已发布知识按 case 文本自动匹配, Case 页浮现候选
        "recall_candidates": _recall_candidates(_case_to_dict(case)),
        # v0.8.5 D4: 复利卡 (诚实计数)
        "reuse_summary": KnowledgeService().case_reuse_summary(case_id),
        "judgments": [j for j in judgments if isinstance(j, dict)] if judgments and isinstance(judgments[0], dict) else [
            j.to_dict() if hasattr(j, "to_dict") else j for j in judgments
        ],
        "actions": [a for a in actions if isinstance(a, dict)] if actions and isinstance(actions[0], dict) else [
            a.to_dict() if hasattr(a, "to_dict") else a for a in actions
        ],
        "runs": [r for r in runs if isinstance(r, dict)] if runs and isinstance(runs[0], dict) else [
            r.to_dict() if hasattr(r, "to_dict") else r for r in runs
        ],
        "artifacts": [a for a in artifacts if isinstance(a, dict)] if artifacts and isinstance(artifacts[0], dict) else [
            a.to_dict() if hasattr(a, "to_dict") else a for a in artifacts
        ],
    }


@router.get("/{case_id}/aggregate")
async def get_case_aggregate_endpoint(
    case_id: str,
    judgments_limit: int = Query(default=50, ge=1, le=200),
    actions_limit: int = Query(default=50, ge=1, le=200),
    runs_per_action: int = Query(default=10, ge=1, le=50),
    artifacts_per_run: int = Query(default=10, ge=1, le=50),
):
    """C11 R19: Case 聚合查询, 1 次拉齐 5 类对象, 避免前端 N+1."""
    return await asyncio.to_thread(
        _aggregate, case_id,
        judgments_limit=judgments_limit, actions_limit=actions_limit,
        runs_per_action=runs_per_action, artifacts_per_run=artifacts_per_run,
    )


@router.get("")
async def list_cases_endpoint(
    status: list[str] | None = Query(default=None),
    priority: list[str] | None = Query(default=None),
    owner_role: str | None = Query(default=None),
    subject_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """列表 — 过滤 status / priority / owner_role / subject_id, 分页 limit/offset."""
    return await asyncio.to_thread(_list, status, priority, owner_role, subject_id, limit, offset)


@router.get("/{case_id}")
async def get_case_endpoint(case_id: str):
    """详情."""
    return await asyncio.to_thread(_get, case_id)


@router.patch("/{case_id}")
async def update_case_endpoint(case_id: str, req: UpdateCaseRequest = Body(...)):
    """CAS 更新 — body 必含 expected_revision."""
    return await asyncio.to_thread(_update, case_id, req)


@router.post("/{case_id}/close", status_code=200)
async def close_case_endpoint(case_id: str, req: CloseCaseRequest = Body(...)):
    """关闭 Case — 校验无 active run, 落 closed_at."""
    return await asyncio.to_thread(_close, case_id, req)
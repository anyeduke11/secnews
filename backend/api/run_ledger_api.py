"""run_ledger_api.py — M1 提案/审批/Run 账本端点 (v0.8.6 P1-1)。

- POST   /api/proposals          创建 draft 提案 (AI/命令/副驾)
- POST   /api/proposals/draft-judgment  Case 页 AI 起草研判 (HEAVY; 失败落 failed 提案)
- POST   /api/proposals/failed   记录 AI 起草失败 (用例 A②, 收件箱可重试)
- GET    /api/proposals          收件箱列表 (?status=&kind=&limit=&offset=)
- GET    /api/proposals/{id}     提案详情
- POST   /api/proposals/{id}/approve  人批准 (可带修订 payload) → 双签 Run
- POST   /api/proposals/{id}/reject   人驳回 (reason 必填 ≤200)

Run 终判 (finish_run) 暂不开放 HTTP — 由后续 pi 执行体/artifact 校验内部调用。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.services.run_ledger_service import RunLedgerService

router = APIRouter(prefix="/api/proposals", tags=["run-ledger"])


class CreateProposalBody(BaseModel):
    source: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    prompt_version: str | None = None
    case_id: str | None = None


class FailedProposalBody(BaseModel):
    source: str
    kind: str
    error: str
    case_id: str | None = None
    prompt_version: str | None = None


class ApproveBody(BaseModel):
    reviewed_by: str
    payload: dict[str, Any] | None = None  # 非空 = 人修订后批准


class RejectBody(BaseModel):
    reviewed_by: str
    # 业务必填 (空/超长由 service 返回 400), 不在 Pydantic 层挡成 422
    reason: str = ""


def _svc() -> RunLedgerService:
    return RunLedgerService()


@router.post("")
def create_proposal(body: CreateProposalBody) -> dict[str, Any]:
    return _svc().create_proposal(
        source=body.source, kind=body.kind, payload=body.payload,
        evidence_ids=body.evidence_ids, prompt_version=body.prompt_version,
        case_id=body.case_id,
    )


class DraftJudgmentBody(BaseModel):
    case_id: str = Field(min_length=1, max_length=64)


@router.post("/draft-judgment")
def draft_judgment(body: DraftJudgmentBody) -> dict[str, Any]:
    """用例 A①: AI 起草研判。成功→draft 提案; 模型失败→failed 提案 (HTTP 200,
    status 字段区分), 无绑定证据→400。同步工作 (内含 asyncio.run 桥) 由
    FastAPI 线程池执行。"""
    return _svc().draft_judgment(body.case_id)


@router.post("/failed")
def record_failed_proposal(body: FailedProposalBody) -> dict[str, Any]:
    return _svc().record_failed_proposal(
        source=body.source, kind=body.kind, error=body.error,
        case_id=body.case_id, prompt_version=body.prompt_version,
    )


@router.get("")
def list_proposals(
    status: str | None = Query(None),
    kind: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    items, total = _svc().list_proposals(
        status=status, kind=kind, limit=limit, offset=offset,
    )
    return {"items": items, "total": total,
            "filter": {"status": status, "kind": kind}}


@router.get("/{proposal_id}")
def get_proposal(proposal_id: str) -> dict[str, Any]:
    return _svc().get_proposal(proposal_id)


@router.post("/{proposal_id}/approve")
def approve_proposal(proposal_id: str, body: ApproveBody) -> dict[str, Any]:
    return _svc().approve_proposal(
        proposal_id, reviewed_by=body.reviewed_by, payload=body.payload,
    )


@router.post("/{proposal_id}/reject")
def reject_proposal(proposal_id: str, body: RejectBody) -> dict[str, Any]:
    return _svc().reject_proposal(
        proposal_id, reviewed_by=body.reviewed_by, reason=body.reason,
    )


__all__ = ["router"]


@router.post("/runs/{run_id}/retry")
def retry_run(run_id: str) -> dict[str, Any]:
    """P1-1 收尾: failed Run 原地重试 (账本 proposal Run 产物化失败场景)。

    人的批准双签已成立; 重试仅复位该 Run 并重走 md 产物化 + sha256 登记,
    重试再失败 Run 保持 failed 且原异常上抛 (500)。非 failed / 非账本
    Run / 提案非 approved → 409/400。
    """
    return _svc().retry_run(run_id)

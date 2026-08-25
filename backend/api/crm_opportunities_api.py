"""CRM 商机路由 (/api/crm/opportunities*, 扩展域 crm, PRD US-2 状态机)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.crm_common import require_crm_token
from backend.repository import crm_customer_repo as customer_repo
from backend.repository import crm_opportunity_repo as repo
from backend.repository.crm_opportunity_repo import InvalidTransitionError

router = APIRouter(prefix="/api/crm/opportunities", dependencies=[Depends(require_crm_token)])


class OpportunityCreate(BaseModel):
    customer_id: int
    name: str = Field(..., min_length=1, max_length=120)
    service_type: str | None = Field(None, max_length=40)
    stage: str | None = Field(None)
    amount: float | None = Field(None, ge=0)
    cost: float | None = Field(None, ge=0)
    owner: str | None = Field(None, max_length=40)
    expected_close_date: str | None = None
    description: str | None = Field(None, max_length=2000)


class OpportunityPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    service_type: str | None = Field(None, max_length=40)
    amount: float | None = Field(None, ge=0)
    cost: float | None = Field(None, ge=0)
    owner: str | None = Field(None, max_length=40)
    expected_close_date: str | None = None
    description: str | None = Field(None, max_length=2000)


class TransitionRequest(BaseModel):
    to_stage: str = Field(..., pattern=f"^{'|'.join(repo.STAGES)}$")
    note: str = Field("", max_length=500)
    lost_reason: str = Field("", max_length=200)


def _serialize(row) -> dict:
    return row.to_dict()


@router.post("", status_code=201)
async def create_opportunity(body: OpportunityCreate) -> dict:
    if customer_repo.get(body.customer_id) is None:
        raise HTTPException(status_code=404,
                            detail={"message": f"客户不存在: {body.customer_id}"})
    try:
        row = repo.create(body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"message": str(e)})
    return _serialize(row)


@router.get("")
async def list_opportunities(
    customer_id: int | None = None, stage: str | None = None,
    owner: str | None = None, limit: int = 200, offset: int = 0,
) -> dict:
    rows = repo.list_all(customer_id=customer_id, stage=stage, owner=owner,
                         limit=min(limit, 500), offset=max(offset, 0))
    return {"items": [_serialize(r) for r in rows], "total": len(rows), "limit": limit}


@router.get("/{opportunity_id}")
async def get_opportunity(opportunity_id: int) -> dict:
    row = repo.get(opportunity_id)
    if row is None:
        raise HTTPException(status_code=404,
                            detail={"message": f"商机不存在: {opportunity_id}"})
    out = _serialize(row)
    out["events"] = repo.events(opportunity_id)
    return out


@router.patch("/{opportunity_id}")
async def patch_opportunity(opportunity_id: int, body: OpportunityPatch) -> dict:
    """非阶段字段更新; 改阶段必须走 /transition (PRD §2 状态机唯一入口)。"""
    if repo.get(opportunity_id) is None:
        raise HTTPException(status_code=404,
                            detail={"message": f"商机不存在: {opportunity_id}"})
    return _serialize(repo.update_fields(opportunity_id, body.model_dump(exclude_none=True)))


@router.post("/{opportunity_id}/transition")
async def transition_opportunity(opportunity_id: int, body: TransitionRequest) -> dict:
    try:
        return _serialize(repo.transition(
            opportunity_id, body.to_stage, note=body.note, lost_reason=body.lost_reason,
        ))
    except LookupError as e:
        raise HTTPException(status_code=404, detail={"message": str(e)})
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})


@router.delete("/{opportunity_id}")
async def delete_opportunity(opportunity_id: int) -> dict:
    return {"deleted": repo.delete(opportunity_id), "id": opportunity_id}


__all__ = ["router"]

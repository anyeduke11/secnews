"""CRM 客户路由 (/api/crm/customers*, 扩展域 crm, PRD US-1)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.crm_common import require_crm_token
from backend.repository import crm_customer_repo as repo
from backend.repository.crm_customer_repo import CrmCustomerExistsError

router = APIRouter(prefix="/api/crm/customers", dependencies=[Depends(require_crm_token)])


class CustomerUpsert(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    industry: str | None = Field(None, max_length=40)
    level: str | None = Field(None, pattern="^[SABCD]$")
    status: str | None = Field(None, pattern="^(活跃|续约中|停滞|流失)$")
    region: str | None = Field(None, max_length=20)
    owner: str | None = Field(None, max_length=40)
    contact_name: str | None = Field(None, max_length=40)
    contact_phone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=120)
    contract_start_date: str | None = None
    contract_end_date: str | None = None
    contract_amount: float | None = Field(None, ge=0)
    nps_score: int | None = Field(None, ge=0, le=10)
    notes: str | None = Field(None, max_length=2000)


class CustomerPatch(BaseModel):
    """PATCH 专用: 全字段可选 (name 仅在提供时参与唯一性校验)。"""

    name: str | None = Field(None, min_length=1, max_length=120)
    industry: str | None = Field(None, max_length=40)
    level: str | None = Field(None, pattern="^[SABCD]$")
    status: str | None = Field(None, pattern="^(活跃|续约中|停滞|流失)$")
    region: str | None = Field(None, max_length=20)
    owner: str | None = Field(None, max_length=40)
    contact_name: str | None = Field(None, max_length=40)
    contact_phone: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=120)
    contract_start_date: str | None = None
    contract_end_date: str | None = None
    contract_amount: float | None = Field(None, ge=0)
    nps_score: int | None = Field(None, ge=0, le=10)
    notes: str | None = Field(None, max_length=2000)


@router.post("", status_code=201)
async def create_customer(body: CustomerUpsert) -> dict:
    try:
        return repo.create(body.model_dump(exclude_none=True)).to_dict()
    except CrmCustomerExistsError:
        raise HTTPException(status_code=409, detail={"message": f"客户已存在: {body.name}"})


@router.get("")
async def list_customers(
    industry: str | None = None, status: str | None = None,
    level: str | None = None, q: str | None = None,
    limit: int = 200, offset: int = 0,
) -> dict:
    rows = repo.list_all(industry=industry, status=status, level=level, q=q,
                         limit=min(limit, 500), offset=max(offset, 0))
    return {"items": [r.to_dict() for r in rows], "total": len(rows), "limit": limit}


@router.get("/{customer_id}")
async def get_customer(customer_id: int) -> dict:
    row = repo.get(customer_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"message": f"客户不存在: {customer_id}"})
    return row.to_dict()


@router.patch("/{customer_id}")
async def update_customer(customer_id: int, body: CustomerPatch) -> dict:
    if repo.get(customer_id) is None:
        raise HTTPException(status_code=404, detail={"message": f"客户不存在: {customer_id}"})
    try:
        row = repo.update(customer_id, body.model_dump(exclude_none=True))
    except CrmCustomerExistsError:
        raise HTTPException(status_code=409, detail={"message": f"客户名已被占用: {body.name}"})
    return row.to_dict()


@router.delete("/{customer_id}")
async def delete_customer(customer_id: int) -> dict:
    """级联删除该客户全部商机与事件 (migration 071 ON DELETE CASCADE)。"""
    return {"deleted": repo.delete(customer_id), "id": customer_id}


__all__ = ["router"]

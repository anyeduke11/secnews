"""v1.0 T08 Case API — 查询路径 (列表 / 详情).

拆自 ``backend/api/case_api.py`` (R3 行数收缩): handler 逻辑逐字搬移,
prefix 由本 router 自带 (惰性展开惯例), URL/method 逐字不变。

- ``GET /api/v1/cases``        列表 — query: status / priority / owner_role / subject_id / limit / offset
- ``GET /api/v1/cases/{id}``   详情
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.api.v1_case_common import _case_to_dict, _list_response
from backend.services.case_service import CaseNotFoundError, CaseService
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/cases", tags=["v1-cases"])


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

"""v1 Knowledge API — 查询路径 (列表 / 详情 / 召回).

拆自 ``backend/api/knowledge_api.py`` (R3 行数收缩): handler 逻辑逐字搬移,
prefix 由本 router 自带 (惰性展开惯例), URL/method 逐字不变。

- ``GET /api/v1/knowledge``                列表 (query: case_id + status/kind/limit/offset)
- ``GET /api/v1/knowledge/{id}``           详情
- ``GET /api/v1/knowledge/{id}/recall``    召回 — 条件比较 + adoption history (?case_id=)
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.api.v1_knowledge_common import _knowledge_to_dict, _list_response
from backend.services.knowledge_service import (
    KnowledgeNotFoundError,
    KnowledgeService,
    KnowledgeValidationError,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/knowledge", tags=["v1-knowledge"])


def _list(case_id: str | None, status: str | None, kind: str | None, limit: int, offset: int) -> dict[str, Any]:
    """T15.5: case_id=None 走 list_all (全局), 非 None 走 list_by_case (T13 路径)."""
    svc = KnowledgeService()
    if case_id is None:
        result = svc.list_all(status=status, kind=kind, limit=limit, offset=offset)
    else:
        result = svc.list_by_case(case_id, status=status, kind=kind, limit=limit, offset=offset)
    return _list_response(result["items"], total=result["total"])


def _get(knowledge_id: str) -> dict[str, Any]:
    svc = KnowledgeService()
    try:
        k = svc.get(knowledge_id)
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    return {"version": API_VERSION, "item": _knowledge_to_dict(k)}


def _recall(knowledge_id: str, case_id: str) -> dict[str, Any]:
    svc = KnowledgeService()
    try:
        result = svc.recall_for_case(case_id, knowledge_id=knowledge_id)
    except KnowledgeNotFoundError as e:
        raise HTTPException(status_code=404, detail={"code": "E_NOT_FOUND", "message": str(e)})
    except KnowledgeValidationError as e:
        raise HTTPException(status_code=400, detail={"code": "E_VALIDATION", "message": str(e)})
    return {"version": API_VERSION, "recall": result}


@router.get("", response_model=None)
async def list_knowledge(
    case_id: str | None = Query(None, max_length=26),
    status: str | None = Query(None),
    kind: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """T15.5: case_id 可选, None 走 list_all (全局)."""
    return await asyncio.to_thread(_list, case_id, status, kind, limit, offset)


@router.get("/{knowledge_id}", response_model=None)
async def get_knowledge(knowledge_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(_get, knowledge_id)


@router.get("/{knowledge_id}/recall", response_model=None)
async def recall_knowledge_for_case(
    knowledge_id: str, case_id: str = Query(..., min_length=1, max_length=26),
) -> dict[str, Any]:
    """召回: 该 knowledge 对给定 case 的适用性 + 条件比较 + adoption 历史."""
    return await asyncio.to_thread(_recall, knowledge_id, case_id)

"""CRM 座舱统计路由 (/api/crm/stats, 扩展域 crm, PRD US-3)。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.crm_common import require_crm_token
from backend.repository import crm_customer_repo as customer_repo
from backend.repository.crm_opportunity_repo import STAGES
from backend.services.crm_stats_service import cockpit_stats

router = APIRouter(prefix="/api/crm", dependencies=[Depends(require_crm_token)])


@router.get("/stats")
async def get_cockpit_stats() -> dict:
    """8 KPI + 3 图表聚合 (口径: docs/COCKPIT_PRD.md §3)。"""
    return cockpit_stats()


@router.get("/meta")
async def crm_meta() -> dict:
    """表单枚举选项 (行业清单来自库内 distinct; 阶段/等级为固定口径)。"""
    return {
        "stages": list(STAGES),
        "levels": ["S", "A", "B", "C"],
        "statuses": ["活跃", "续约中", "停滞", "流失"],
        "industries": customer_repo.industries(),
    }


__all__ = ["router"]

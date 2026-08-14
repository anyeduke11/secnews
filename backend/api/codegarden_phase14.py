"""Phase 14 子系统联动 API 端点 — 技术栈漂移评估 + CVE 同步.

路由清单 (spec §4)
-----------------
- POST /api/codegarden/drift/assess             触发 tech_stack drift 评估
- GET  /api/codegarden/drift/assessments         获取 drift 评估列表
- PUT  /api/codegarden/drift/assessments/{id}    更新评估状态
- POST /api/cve/sync                             触发 CVE 双向同步

设计原则
--------
- 同步 DB 操作通过 asyncio.to_thread 包装
- 错误统一用 HTTPException + 中文 message
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.exceptions import InternalException
from backend.logging_config import logger
from backend.services.codegarden_drift import (
    VALID_DRIFT_STATUSES,
    assess_drift,
    get_assessments,
    update_assessment_status,
)
from backend.services.cve_knowledge_sync import sync_cve_to_security

router = APIRouter(tags=["codegarden-phase14"])


# ===========================================================================
# Request / Response models
# ===========================================================================
class UpdateDriftStatusRequest(BaseModel):
    status: str = Field(..., description=f"新状态: {', '.join(VALID_DRIFT_STATUSES)}")
    notes: str | None = Field(None, description="备注")


# ===========================================================================
# Tech Stack Drift 评估 (3 端点)
# ===========================================================================
@router.post("/api/codegarden/drift/assess")
async def trigger_drift_assess():
    """触发 tech_stack drift 评估.

    扫描 knowledge_items 的 item_entities(entity_type='tool'),
    对比 cg_projects.tech_stack, 发现新 tech 时写入 cg_drift_assessments.
    """
    try:
        report = await asyncio.to_thread(assess_drift)
        return report
    except InternalException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"drift assess failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/codegarden/drift/assessments")
async def list_drift_assessments(
    status: str | None = Query(None, description=f"筛选状态: {', '.join(VALID_DRIFT_STATUSES)}"),
    project_id: str | None = Query(None, description="筛选项目 ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """获取 drift 评估列表."""
    try:
        return await asyncio.to_thread(
            get_assessments,
            status=status, project_id=project_id,
            limit=limit, offset=offset,
        )
    except Exception as e:
        logger.error(f"list drift assessments failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/codegarden/drift/assessments/{assessment_id}")
async def update_drift_assessment(
    assessment_id: int,
    req: UpdateDriftStatusRequest,
):
    """更新评估状态 (reviewed/applied/dismissed)."""
    try:
        result = await asyncio.to_thread(
            update_assessment_status,
            assessment_id=assessment_id,
            status=req.status,
            notes=req.notes,
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"assessment {assessment_id} 不存在",
            )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"update drift assessment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# CVE 同步 (1 端点)
# ===========================================================================
@router.post("/api/cve/sync")
async def trigger_cve_sync():
    """触发 CVE 双向同步: item_entities(entity_type='cve') → security_entities."""
    try:
        report = await asyncio.to_thread(sync_cve_to_security)
        return report
    except InternalException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"CVE sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ["router"]
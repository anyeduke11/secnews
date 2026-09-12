"""Knowledge API — skills endpoints (Phase 7 后全部 deprecated)。

拆自 ``backend/api/knowledge.py`` (Batch 2 任务 A): handler 逻辑原样搬移,
路径相对聚合层 (聚合层带 ``/api/knowledge`` prefix), URL 逐字不变。

Phase 7: skill_config_service 已删除 (Phase 5 内部 hotspot-agent 依赖)
skills 端点降级为 deprecated, 除 GET /skills 返回空列表外永远 410 Gone。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/skills/{skill_name}/validate")
async def validate_skill(skill_name: str):
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回 410 Gone。"""
    raise HTTPException(
        status_code=410,
        detail={
            "message": "skill_config table dropped in v1.7.6 (Phase 7)",
            "migration": "migration 038",
        },
    )


@router.get("/skills")
async def list_skills(enabled: bool | None = Query(None)):
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回空列表。"""
    return {"version": API_VERSION, "deprecated": True, "skills": []}


@router.post("/skills")
async def create_skill(data: dict):
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回 410 Gone。"""
    raise HTTPException(
        status_code=410,
        detail={"message": "skill_config dropped in v1.7.6 (Phase 7)"},
    )


@router.patch("/skills/{skill_id}")
async def update_skill(skill_id: int, data: dict):
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回 410 Gone。"""
    raise HTTPException(
        status_code=410,
        detail={"message": "skill_config dropped in v1.7.6 (Phase 7)"},
    )


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: int):
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回 410 Gone。"""
    raise HTTPException(
        status_code=410,
        detail={"message": "skill_config dropped in v1.7.6 (Phase 7)"},
    )


@router.post("/skills/seed")
async def seed_skills():
    """[DEPRECATED] Phase 7 后 skills 不可用, 永远返回 410 Gone。"""
    raise HTTPException(
        status_code=410,
        detail={"message": "skill_config dropped in v1.7.6 (Phase 7)"},
    )

"""S4-4 合规矩阵 API — 等保 2.0 + GDPR + ISO 27001。

路由:
- GET /api/compliance/frameworks
- GET /api/compliance/matrix?event_types=...&frameworks=...
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from backend.services.compliance_service import controls_for_event, list_frameworks, matrix

router = APIRouter()


@router.get("/compliance/frameworks")
async def get_frameworks() -> dict[str, Any]:
    """返回可用合规框架列表。"""
    frameworks = list_frameworks()
    return {"frameworks": frameworks}


@router.get("/compliance/matrix")
async def get_compliance_matrix(
    event_types: str = Query("", description="逗号分隔的事件类型列表"),
    frameworks: str = Query("", description="逗号分隔的框架 ID 过滤 (可选)"),
) -> dict[str, Any]:
    """返回事件 × 合规控制项矩阵。"""
    event_list = [e.strip() for e in event_types.split(",") if e.strip()]
    framework_list = [f.strip() for f in frameworks.split(",") if f.strip()] or None
    return matrix(event_list, framework_list)


@router.get("/compliance/controls/{event_type}")
async def get_controls_for_event(event_type: str) -> dict[str, Any]:
    """返回某事件类型对应的控制项列表。"""
    controls = controls_for_event(event_type)
    return {"event_type": event_type, "controls": controls}


__all__ = ["router"]

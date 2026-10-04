"""quality_api.py — /api/quality: 质量门禁拒收回放 (v0.8.6 P1-5, 审计 F1-3)。

- GET /api/quality/rejections?hours=&limit=
    strict 模式真实拒收 (hard gate fail / score < min_score, pipeline 在
    raise 前写的 gate_name='pipeline' 标记行) LEFT JOIN raw_items 原文
    (title/url/summary/source) — 验收 "任取一条拒绝, 可在 UI 看到原文与原因"。

只读; SQL 下沉 QualityLogRepository.list_rejections (R2)。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from backend.repository.quality_repo import QualityLogRepository

router = APIRouter(prefix="/api/quality", tags=["quality"])


@router.get("/rejections")
def list_rejections(
    hours: int = Query(168, ge=1, le=24 * 30, description="回看窗口"),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    items, total = QualityLogRepository().list_rejections(
        hours=hours, limit=limit,
    )
    return {"items": items, "total": total, "window_hours": hours}


__all__ = ["router"]

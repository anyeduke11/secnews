"""v1.0 T15 Signal API (Intel 入口真实化)."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query

from backend.services.signal_service import list_recent_signals
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/v1/signals", tags=["v1-signals"])


def _list(case_id: str | None = None, days: int = 7, limit: int = 50) -> dict[str, Any]:
    items = list_recent_signals(days=days, case_id=case_id, limit=limit)
    return {
        "version": API_VERSION,
        "items": items,
        "total": len(items),
        "days": days,
    }


@router.get("", response_model=None)
async def list_signals(
    case_id: str | None = Query(None, max_length=26),
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    return await asyncio.to_thread(_list, case_id, days, limit)

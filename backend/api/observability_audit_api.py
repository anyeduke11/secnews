"""v1.0 T16 收口 — audit_log 查询 API (GET /api/observability/audit).

T16 LegacyMigrateService 写完 audit_log 后, 提供查询端点验证.
复用 observability_records 表 (actor/action/target/detail/trace_id/occurred_at), 走原 observability_router 路由前缀 /api/observability.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Query

from backend.repository.db import get_connection
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/observability/audit", tags=["observability-audit"])


def _list(action: str | None, limit: int) -> dict[str, Any]:
    """列 audit_log 最近 N 条 (按 occurred_at DESC); action 可选过滤."""
    conn = get_connection()
    if action:
        rows = conn.execute(
            "SELECT actor, action, target, detail, occurred_at "
            "FROM audit_log WHERE action = ? ORDER BY occurred_at DESC LIMIT ?",
            (action, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT actor, action, target, detail, occurred_at "
            "FROM audit_log ORDER BY occurred_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    items = []
    for r in rows:
        item = {
            "actor": r[0], "action": r[1], "target": r[2],
            "occurred_at": r[4],
        }
        try:
            item["detail"] = json.loads(r[3]) if r[3] else {}
        except (json.JSONDecodeError, TypeError):
            item["detail"] = r[3]
        items.append(item)
    return {"version": API_VERSION, "items": items, "total": len(items)}


@router.get("", response_model=None)
async def list_audit(
    action: str | None = Query(None, description="action 过滤 (e.g. 'skill.deprecated')"),
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    """T16 收口: 列 audit_log 最近 N 条 (T16 service 写完后能查 skill.deprecated 等)."""
    return await asyncio.to_thread(_list, action, limit)

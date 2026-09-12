"""v1.0 T16 收口 — audit_log 查询 API (GET /api/observability/audit).

T16 LegacyMigrateService 写完 audit_log 后, 提供查询端点验证.
复用 observability_records 表 (actor/action/target/detail/trace_id/occurred_at), 走原 observability_router 路由前缀 /api/observability.
SQL 下沉 backend/services/observability_query_service.query_audit_log_items (Batch 2), 本层只做响应组装.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query

from backend.services.observability_query_service import query_audit_log_items
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/observability/audit", tags=["observability-audit"])


@router.get("", response_model=None)
async def list_audit(
    action: str | None = Query(None, description="action 过滤 (e.g. 'skill.deprecated')"),
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    """T16 收口: 列 audit_log 最近 N 条 (T16 service 写完后能查 skill.deprecated 等)."""
    items = await asyncio.to_thread(query_audit_log_items, action, limit)
    return {"version": API_VERSION, "items": items, "total": len(items)}

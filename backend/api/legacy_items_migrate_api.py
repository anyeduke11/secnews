"""v1.0 T18 旧 knowledge_items 数据迁移 API (POST /api/dsh/legacy/items/migrate/run).

对齐 T16 LegacyMigrate API 形态 (/api/dsh/legacy/* + /api/dsh/legacy/items/*):
  - POST /api/dsh/legacy/items/migrate/run?apply=false → dry-run counts
  - POST /api/dsh/legacy/items/migrate/run?apply=true  → 真落 (走 WARM_DB → v1_knowledge)
  - GET  /api/dsh/legacy/items/migrate/status               → 上次结果状态 (内存无缓存, 走 service.run 重返 dry-run counts)
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query

from backend.services.legacy_items_migrate_service import (
    LegacyItemsMigrateResult,
    LegacyItemsMigrateService,
)
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/dsh/legacy/items/migrate", tags=["legacy-items-migrate"])


def _run(apply: bool) -> dict[str, Any]:
    svc = LegacyItemsMigrateService()
    r: LegacyItemsMigrateResult = svc.migrate_legacy_items(apply=apply)
    return {
        "version": API_VERSION,
        "mode": "apply" if apply else "dry-run",
        "result": r.to_dict(),
    }


def _status() -> dict[str, Any]:
    """返 dry-run counts (T18 内存无缓存, 走 service 重返 dry-run; T19 收口补 cache)."""
    svc = LegacyItemsMigrateService()
    r = svc.migrate_legacy_items(apply=False)
    return {
        "version": API_VERSION,
        "warm_db_candidates": r.items_candidates,
        "sample_ids": r.sample_ids,
    }


@router.post("/run", response_model=None)
async def run_items_migration(
    apply: bool = Query(False, description="True = 真落 (走 WARM_DB → v1_knowledge), False = dry-run 仅计数"),
) -> dict[str, Any]:
    return await asyncio.to_thread(_run, apply)


@router.get("/status", response_model=None)
async def items_migration_status() -> dict[str, Any]:
    return await asyncio.to_thread(_status)

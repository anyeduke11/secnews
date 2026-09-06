"""v1.0 T16 收口 — LegacyMigrateService API 暴露 (POST /api/dsh/legacy/migrate/run).

对齐 T08 legacy_hold_service 端点形态 (/api/dsh/legacy/*):
  - POST /api/dsh/legacy/migrate/run?apply=false → dry-run (返 counts)
  - POST /api/dsh/legacy/migrate/run?apply=true  → 真落 (返 applied/skipped)
  - GET  /api/dsh/legacy/migrate/status               → 内存态查询 (BUILTIN legacy_v0 → deprecated 计数)

T16 仅 CLI (`scripts/t16_legacy_migrate.py`); T16 收口补 API 端点.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query

from backend.services.legacy_migrate_service import LegacyMigrateService
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/dsh/legacy/migrate", tags=["legacy-migrate"])


def _run(apply: bool) -> dict[str, Any]:
    svc = LegacyMigrateService()
    r = svc.run(apply=apply)
    return {
        "version": API_VERSION,
        "mode": "apply" if apply else "dry-run",
        "result": r.to_dict(),
    }


def _status() -> dict[str, Any]:
    """BUILTIN 内存态: 旧 20 SK 已 deprecated 计数 (T16 apply 后状态)."""
    from backend.services.skill_registry.builtin import BUILTIN
    items = BUILTIN.list()
    legacy_v0 = sum(1 for s in items if getattr(s, "status", None) == "legacy_v0")
    deprecated = sum(1 for s in items if getattr(s, "status", None) == "deprecated")
    v1_active = sum(1 for s in items if getattr(s, "status", None) == "v1_active")
    return {
        "version": API_VERSION,
        "builtin_total": len(items),
        "status_breakdown": {
            "legacy_v0": legacy_v0,
            "deprecated": deprecated,
            "v1_active": v1_active,
        },
    }


@router.post("/run", response_model=None)
async def run_migration(
    apply: bool = Query(False, description="True = 真落, False = dry-run 仅计数"),
) -> dict[str, Any]:
    return await asyncio.to_thread(_run, apply)


@router.get("/status", response_model=None)
async def migration_status() -> dict[str, Any]:
    return await asyncio.to_thread(_status)

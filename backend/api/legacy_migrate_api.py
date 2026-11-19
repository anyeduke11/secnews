"""v1.0 T16 收口 — LegacyMigrateService API 暴露 (POST /api/dsh/legacy/migrate/run).

对齐 T08 遗留票据收口端点形态 (/api/dsh/legacy/*):
  - POST /api/dsh/legacy/migrate/run?apply=false → dry-run (返 counts)
  - POST /api/dsh/legacy/migrate/run?apply=true  → 真落 (返 applied/skipped)

T16 仅 CLI (`scripts/t16_legacy_migrate.py`); T16 收口补 API 端点.
2026-11-19: GET /status (BUILTIN SK 计数) 随技能域删除退役.
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


@router.post("/run", response_model=None)
async def run_migration(
    apply: bool = Query(False, description="True = 真落, False = dry-run 仅计数"),
) -> dict[str, Any]:
    return await asyncio.to_thread(_run, apply)

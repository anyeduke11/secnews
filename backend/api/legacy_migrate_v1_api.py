"""v1.0 C13 收口 — LegacyMigrateServiceV1 API 暴露 (5 端点, 3 源独立 + mapping 表 + promote).

C13 plan §3.1: 新建 legacy_migrate_v1_api.py, 旧 API (/api/dsh/legacy/migrate/* + /api/dsh/legacy/items/migrate/*)
保留向后兼容 (T16/T18 薄壳委派 v1).

端点:
  - POST /api/dsh/legacy/migrate/v1/run?source=seed|warm|wiki&apply=false|true&batch_id=&offset=&limit=
  - GET  /api/dsh/legacy/migrate/v1/status?batch_id=  — 走 v1_legacy_mapping 真实查询
  - GET  /api/dsh/legacy/migrate/v1/mapping?legacy_source=&legacy_id=&status=&limit=
  - POST /api/dsh/legacy/migrate/v1/promote  — 触发后台 promote (admin 守卫)
  - GET  /api/dsh/legacy/migrate/v1/promote/log?new_id=&limit=
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Query

from backend.services.legacy_migrate_v1 import LegacyMigrateServiceV1
from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/dsh/legacy/migrate/v1", tags=["legacy-migrate-v1"])


# ---------------------------------------------------------------------------
# 1) run — 3 源独立迁移
# ---------------------------------------------------------------------------
def _run(
    source: str, apply: bool, batch_id: str | None,
    offset: int, limit: int,
) -> dict[str, Any]:
    svc = LegacyMigrateServiceV1()
    if source == "seed":
        batch = svc.migrate_seed(apply=apply, batch_id=batch_id or "api-seed")
    elif source == "warm":
        batch = svc.migrate_warm(
            apply=apply, batch_id=batch_id or "api-warm",
            offset=offset, limit=limit,
        )
    elif source == "wiki":
        batch = svc.migrate_wiki(apply=apply, batch_id=batch_id or "api-wiki")
    elif source == "all":
        # 顺序: seed → warm (全量) → wiki; 串行保证 batch_id 一致便于追踪
        bid = batch_id or "api-all"
        seed_batch = svc.migrate_seed(apply=apply, batch_id=bid + "-seed")
        warm_batch = svc.migrate_warm(
            apply=apply, batch_id=bid + "-warm", offset=offset, limit=limit,
        )
        wiki_batch = svc.migrate_wiki(apply=apply, batch_id=bid + "-wiki")
        return {
            "version": API_VERSION,
            "mode": "apply" if apply else "dry-run",
            "source": source,
            "result": {
                "seed": seed_batch.to_dict(),
                "warm": warm_batch.to_dict(),
                "wiki": wiki_batch.to_dict(),
            },
        }
    else:
        return {"error": f"unknown source: {source}", "version": API_VERSION}
    return {
        "version": API_VERSION,
        "mode": "apply" if apply else "dry-run",
        "source": source,
        "result": batch.to_dict(),
    }


@router.post("/run", response_model=None)
async def run_migration(
    source: str = Query("seed", description="seed | warm | wiki | all"),
    apply: bool = Query(False, description="True = 真落, False = dry-run"),
    batch_id: str | None = Query(None, description="幂等游标 (留 None 自动生成)"),
    offset: int = Query(0, description="warm 分页起点 (ASC 游标)"),
    limit: int = Query(500, description="warm 分页大小"),
) -> dict[str, Any]:
    return await asyncio.to_thread(_run, source, apply, batch_id, offset, limit)


# ---------------------------------------------------------------------------
# 2) status — 走 v1_legacy_mapping 真实查询 (替换 T18 in-memory)
# ---------------------------------------------------------------------------
def _status(batch_id: str | None) -> dict[str, Any]:
    data = LegacyMigrateServiceV1().mapping_status(batch_id)
    return {
        "version": API_VERSION,
        "batch_id": batch_id,
        **data,
    }


@router.get("/status", response_model=None)
async def migration_status(
    batch_id: str | None = Query(None, description="按 batch_id 过滤; None = 全量"),
) -> dict[str, Any]:
    return await asyncio.to_thread(_status, batch_id)


# ---------------------------------------------------------------------------
# 3) mapping — 映射表查询
# ---------------------------------------------------------------------------
def _mapping(
    legacy_source: str | None, legacy_id: str | None,
    status: str | None, limit: int,
) -> dict[str, Any]:
    rows = LegacyMigrateServiceV1().query_mapping(legacy_source, legacy_id, status, limit)
    return {
        "version": API_VERSION,
        "rows": rows,
    }


@router.get("/mapping", response_model=None)
async def query_mapping(
    legacy_source: str | None = Query(None, description="dev_seed | warm.knowledge_items | wiki_items"),
    legacy_id: str | None = Query(None),
    status: str | None = Query(None, description="applied | awaiting_review | quarantined | skipped | failed"),
    limit: int = Query(50, le=500),
) -> dict[str, Any]:
    return await asyncio.to_thread(_mapping, legacy_source, legacy_id, status, limit)


# ---------------------------------------------------------------------------
# 4) promote — 触发后台 promote (admin 守卫)
# ---------------------------------------------------------------------------
def _promote() -> dict[str, Any]:
    svc = LegacyMigrateServiceV1()
    batch = svc.run_legacy_promote()
    return {
        "version": API_VERSION,
        "result": batch.to_dict(),
    }


@router.post("/promote", response_model=None)
async def trigger_promote() -> dict[str, Any]:
    return await asyncio.to_thread(_promote)


# ---------------------------------------------------------------------------
# 5) promote/log — promote 日志
# ---------------------------------------------------------------------------
def _promote_log(new_id: str | None, limit: int) -> dict[str, Any]:
    rows = LegacyMigrateServiceV1().promote_log(new_id, limit)
    return {
        "version": API_VERSION,
        "rows": rows,
    }


@router.get("/promote/log", response_model=None)
async def query_promote_log(
    new_id: str | None = Query(None),
    limit: int = Query(50, le=500),
) -> dict[str, Any]:
    return await asyncio.to_thread(_promote_log, new_id, limit)

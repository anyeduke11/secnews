"""Maintenance API — DB 健康 / 维护 / 去重 / 保留策略, 薄聚合层 (拆自 184 行单文件)。

路由按资源域拆为子文件, 本文件只负责组装; URL/method 逐字不变,
``backend/api/_registry_core.py`` 无需改动 (惯例同 sources.py / knowledge.py):

- ``maintenance_db_api.py``        — DB 健康/维护/去重 (/health · /table-stats ·
  /dirty-report · /index-health · /vacuum · /cleanup · /orphans · /duplicates ·
  /cleanup-duplicates)
- ``maintenance_retention_api.py`` — 保留策略/备份链 (/backup-verify ·
  /quality-log-tiers · /cleanup-quality-logs · /backups · /backups/compact)

注意: prefix 由每个子 router 自带 (沿用本目录惯例, 见 sources.py),
而非挂在聚合 router 上 — 本仓 FastAPI 的 include 是惰性 _IncludedRouter,
prefix 挂聚合层会推迟到请求期才展开, 破坏 test_feature_gates 的静态路由遍历。
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.maintenance_db_api import router as db_router
from backend.api.maintenance_retention_api import router as retention_router

router = APIRouter()

router.include_router(db_router)
router.include_router(retention_router)

__all__ = ["router"]
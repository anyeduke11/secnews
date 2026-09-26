"""Phase 8 Addendum 8.4+: 信源管理 API — 薄聚合层 (Batch 3 R3, 拆自 582 行单文件)。

路由按资源域拆为子文件, 本文件只负责组装; URL/method 逐字不变,
``backend/api/_registry.py`` 无需改动 (惯例同 Batch 2 knowledge.py):

- ``source_custom_api.py`` — 自定义信源 CRUD (list/add/delete/toggle)
- ``source_probe_api.py``  — 探测/分类 helpers (SSRF 兜底) + custom 重探
- ``source_health_api.py`` — Phase 9 质量门禁 (/health + by-source + reset/dead)
- ``source_trend_api.py``  — Phase 4 产出趋势 (green/yellow/red)
- ``source_stats_api.py``  — Phase 3 调度域 (health/v2 + stats + alerts + 手动探活)
- ``source_system_api.py`` — 治理 T2: 系统源手动管理 (GET/DELETE/PATCH, 审计强制)

注意: prefix 由每个子 router 自带 (沿用本目录惯例, 见 knowledge.py),
而非挂在聚合 router 上 — 本仓 FastAPI 的 include 是惰性 _IncludedRouter,
prefix 挂聚合层会推迟到请求期才展开, 破坏 test_feature_gates 的静态路由遍历。
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.source_custom_api import router as custom_router
from backend.api.source_health_api import router as health_router
from backend.api.source_probe_api import router as probe_router
from backend.api.source_stats_api import router as stats_router
from backend.api.source_system_api import router as system_router
from backend.api.source_trend_api import router as trend_router

router = APIRouter()

router.include_router(custom_router)
router.include_router(probe_router)
router.include_router(health_router)
router.include_router(trend_router)
router.include_router(stats_router)
# 治理 T2: 经本聚合层挂载 → _registry.py 零改动, 90 routers 计数净零
router.include_router(system_router)

__all__ = ["router"]

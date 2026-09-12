"""Knowledge API — thin aggregation layer (Batch 2 任务 A, 拆自 711 行单文件)。

路由按资源域拆为子文件, 本文件只负责组装; URL/method 逐字不变,
``backend/api/_registry.py`` 无需改动:

- ``knowledge_items.py``    — items CRUD + topics + federated search
- ``knowledge_concepts.py`` — concepts + graph + federation + concepts/link/batch
- ``knowledge_ops.py``      — sync + tasks + health
- ``knowledge_import.py``   — bookmarks/import + import-from-history + soul + compile + classify
- ``knowledge_skills.py``   — skills (Phase 7 后 deprecated) + seed + validate
- ``knowledge_obsidian.py`` — obsidian vault + watchdog
- ``knowledge_plans.py``    — learning plans + progress + summaries

注意: prefix 由每个子 router 自带 (沿用本目录惯例, 见 knowledge_imported.py),
而非挂在聚合 router 上 — 本仓 FastAPI 的 include 是惰性 _IncludedRouter,
prefix 挂聚合层会推迟到请求期才展开, 破坏 test_feature_gates 的静态路由遍历。
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.knowledge_concepts import router as concepts_router
from backend.api.knowledge_import import router as import_router
from backend.api.knowledge_items import router as items_router
from backend.api.knowledge_obsidian import router as obsidian_router
from backend.api.knowledge_ops import router as ops_router
from backend.api.knowledge_plans import router as plans_router
from backend.api.knowledge_skills import router as skills_router

router = APIRouter()

router.include_router(items_router)
router.include_router(concepts_router)
router.include_router(ops_router)
router.include_router(import_router)
router.include_router(skills_router)
router.include_router(obsidian_router)
router.include_router(plans_router)

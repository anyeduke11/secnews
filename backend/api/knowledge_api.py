"""v1.0 T13/C12 Knowledge API — thin aggregation layer (R3 行数收缩, 拆自 352 行单文件)。

路由按资源族拆为子文件, 本文件只负责组装; URL/method 逐字不变,
``backend/api/_registry.py`` 无需改动:

- ``v1_knowledge_write_api.py`` — generate + publish/deprecate/retract (T13 生命周期写)
- ``v1_knowledge_query_api.py`` — 列表 / 详情 / recall (查询 + 召回)
- ``v1_knowledge_reuse_api.py`` — reuse / adopt / adoptions / outcome (C12 R16 采用与复用)
- ``v1_knowledge_common.py``    — 共享序列化 helper (不入路由)

注意: prefix 由每个子 router 自带 (沿用本目录惯例, 见 knowledge.py 聚合层),
而非挂在聚合 router 上 — 本仓 FastAPI 的 include 是惰性 _IncludedRouter,
prefix 挂聚合层会推迟到请求期才展开, 破坏 test_feature_gates 的静态路由遍历。
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.v1_knowledge_query_api import router as query_router
from backend.api.v1_knowledge_reuse_api import router as reuse_router
from backend.api.v1_knowledge_write_api import router as write_router

router = APIRouter()

router.include_router(write_router)
router.include_router(query_router)
router.include_router(reuse_router)

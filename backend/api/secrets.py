"""Phase 41 密钥管理 API — 薄聚合层 (Batch 3 R3, 拆自 557 行单文件)。

路由按资源域拆为子文件, 本文件只负责组装; URL/method 逐字不变,
``backend/api/_registry.py`` 无需改动 (惯例同 Batch 2 knowledge.py):

- ``secrets_lifecycle_api.py`` — status/setup/unlock/lock + 共用 ``_err_to_http``
- ``secrets_oauth_api.py``     — OAuth 解锁 (D1 Batch ⑧, 不解密双因素)
- ``secrets_keys_api.py``      — 密钥 CRUD (list/create/update/delete)
- ``secrets_reveal_api.py``    — reveal (现场验证 master_key, 强审计) + test
- ``secrets_rotation_api.py``  — 主密钥轮换 + export/import
- ``secrets_reset_api.py``     — admin 紧急清空 (二次确认 + 来源门禁)

注意: prefix 由每个子 router 自带 (沿用本目录惯例, 见 knowledge.py),
而非挂在聚合 router 上 — 本仓 FastAPI 的 include 是惰性 _IncludedRouter,
prefix 挂聚合层会推迟到请求期才展开, 破坏 test_feature_gates 的静态路由遍历。
安全语义 (掩码/审计/门禁) 逐字搬移未改写, 各子文件行数均 ≤150。
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.api.secrets_keys_api import router as keys_router
from backend.api.secrets_lifecycle_api import router as lifecycle_router
from backend.api.secrets_oauth_api import router as oauth_router
from backend.api.secrets_reset_api import router as reset_router
from backend.api.secrets_reveal_api import router as reveal_router
from backend.api.secrets_rotation_api import router as rotation_router

router = APIRouter()

router.include_router(lifecycle_router)
router.include_router(oauth_router)
router.include_router(keys_router)
router.include_router(reveal_router)
router.include_router(rotation_router)
router.include_router(reset_router)

__all__ = ["router"]

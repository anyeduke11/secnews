"""API 路由注册表 — 拆自 ``backend/api/__init__.py`` (P0-2, v0.6.2)。

原 188 行 __init__.py 拆为:

- ``__init__.py``        — 薄壳, 仅暴露 ``register_routers`` 公开 API (≤ 30 行)
- ``_registry.py`` (本文) — 实际分组与 ``app.include_router`` 调用

约束: 任何 ``from backend.api import register_routers`` / ``backend.api.register_routers`` 仍可解析。

DEV-0287 (债务工单 D5): 291 行超 R3 豁免上限 271 (DEV-0280 注册增长) —
按域分组拆三半 (各自 ≤150 行, 全部脱离豁免清单):
- ``_registry_core.py``       — core 无条件注册区
- ``_registry_flags.py``      — feature flag 接线区 (+ MCP/wiki/LLM/ops 基础设施)
- ``_registry_extensions.py`` — SecNews/DSH/skill_registry/v1 端到端区
本文件只剩 ``register_all`` 编排壳 (先后顺序 = 原文件顺序, URL/method 零变更);
豁免清单条目 ``_registry.py`` 相应删除 (守卫单调收缩)。
"""
from __future__ import annotations

from fastapi import FastAPI


def register_all(app: FastAPI) -> None:
    """注册全部 APIRouter (v1.7+: 含 tags + extract)。

    v1.8 加固: config.feature_* flag 在此接线 —— flag=False 的功能
    router 不注册, 对外不可达 (此前 flag 与注册脱钩, 形同虚设)。
    """
    from backend.api._registry_core import register_core
    from backend.api._registry_extensions import register_extensions
    from backend.api._registry_flags import register_flags

    register_core(app)
    register_flags(app)
    register_extensions(app)


__all__ = ["register_all"]

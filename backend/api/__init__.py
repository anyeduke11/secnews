"""Phase 4 API routers — 入口薄壳 (P0-2, v0.6.2)。

- :func:`register_routers` 委托 ``_registry.register_all`` (188 行 → 薄壳 + 模块化)
- 路由模块文件 ≤ 150 行 (backend/api/AGENTS.md 约束); 注册表本身无此限制
- 所有 import 仍在 register_routers 内部完成, 避免模块级循环依赖
"""
from __future__ import annotations

from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    """公开 API: 注册全部 APIRouter (委托 ``_registry.register_all``)。"""
    from backend.api._registry import register_all
    register_all(app)


__all__ = ["register_routers"]

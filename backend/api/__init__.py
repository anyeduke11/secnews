"""Phase 4 API routers.

- :func:`register_routers` 把 7 个 APIRouter 一次性注册到 FastAPI app

每个 router 文件不超过 150 行；这里的导入是 lazy 的（不在模块级
触发 import，避免 import 循环）。
"""
from __future__ import annotations

from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    """注册全部 17 个 APIRouter (v1.5+: 含 codegarden)。"""
    from backend.api import (
        categories,
        codegarden,  # v1.5+: CodeGarden 代码花园
        content,  # v1.4: 内容创作 (calendar/drafts/templates)
        export,
        favorites,
        health,
        history,
        hotspots,
        knowledge,  # v1.4: 知识库
        maintenance,  # v1.4: DB 维护 (vacuum/cleanup)
        proxy,
        quality,
        refresh,  # Phase 32: POST /api/refresh 手动触发采集
        secrets,  # Phase 41: 密钥管理 (LLM API Keys)
        skills,  # Phase 41: Skill 管理
        sources,
        sync,    # Phase 42: 跨端配置同步 (WebDAV)
        todos,   # Phase 36: /api/todos 待办 (Todos) CRUD
        trends,
        weekly_report,  # v1.3.0 Phase 4: 周报
    )

    app.include_router(hotspots.router, tags=["hotspots"])
    app.include_router(trends.router, tags=["trends"])
    app.include_router(categories.router, tags=["categories"])
    app.include_router(health.router, tags=["health"])
    app.include_router(export.router, tags=["export"])
    app.include_router(proxy.router, tags=["proxy"])
    app.include_router(quality.router, tags=["quality"])
    app.include_router(sources.router, tags=["sources"])
    app.include_router(favorites.router, tags=["favorites"])
    app.include_router(history.router, tags=["history"])
    app.include_router(refresh.router, tags=["refresh"])
    app.include_router(todos.router, tags=["todos"])
    app.include_router(skills.router, tags=["skills"])
    app.include_router(secrets.router, tags=["secrets"])
    app.include_router(sync.router, tags=["sync"])
    app.include_router(weekly_report.router, tags=["weekly-report"])
    app.include_router(knowledge.router, tags=["knowledge"])
    app.include_router(content.router, tags=["content"])
    app.include_router(maintenance.router, tags=["maintenance"])
    app.include_router(codegarden.router, tags=["codegarden"])


__all__ = ["register_routers"]

"""Phase 4 API routers.

- :func:`register_routers` 把 7 个 APIRouter 一次性注册到 FastAPI app

每个 router 文件不超过 150 行；这里的导入是 lazy 的（不在模块级
触发 import，避免 import 循环）。
"""
from __future__ import annotations

from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    """注册全部 APIRouter (v1.7+: 含 tags + extract)。"""
    # 注意: annotations 必须用 `import ... as` 显式导入子模块,
    # 因为模块顶部的 `from __future__ import annotations` 会把 `annotations`
    # 绑定为 _Feature 实例, 导致 `from backend.api import annotations` 拿到 _Feature 而非子模块.
    import backend.api.annotations as annotations_api  # v1.7 Phase 2: 笔记空间
    from backend.api import (
        alerts,  # v1.7 Phase 3: 告警规则与告警
        categories,
        digests,  # v1.7 Phase 4: 简报
        mode,  # v1.7 Phase 3: 模式切换 (brief/scan/deep/...)
        recommend,  # v1.7 Phase 4: 上下文推荐
        search,  # v1.7 Phase 3: 统一跨层搜索
        codegarden,  # v1.5+: CodeGarden 代码花园 (Phase 2a)
        codegarden_phase2b,  # v1.5+: CodeGarden Phase 2b (services/resources/events)
        content,  # v1.4: 内容创作 (calendar/drafts/templates)
        events,  # v1.3.0 Phase 6: SSE 实时推送
        export,
        extract,  # v1.7 Phase 1: 标签自动提取
        favorites,
        health,
        history,
        hotspots,
        knowledge,  # v1.4: 知识库
        maintenance,  # v1.4: DB 维护 (vacuum/cleanup)
        proxy,
        quality,
        refresh,  # Phase 32: POST /api/refresh 手动触发采集
        reviews,  # v1.7 Phase 2: SM-2 间隔复习
        secrets,  # Phase 41: 密钥管理 (LLM API Keys)
        security,  # Phase 2: Security Knowledge Graph + Terminology
        skills,  # Phase 41: Skill 管理
        sources,
        sync,    # Phase 42: 跨端配置同步 (WebDAV)
        tags,  # v1.7 Phase 1: 标签管理
        tech_stack,  # v1.7 Phase 2: 技术栈 + 项目桥接
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
    app.include_router(security.router, tags=["security"])
    app.include_router(sync.router, tags=["sync"])
    app.include_router(weekly_report.router, tags=["weekly-report"])
    app.include_router(knowledge.router, tags=["knowledge"])
    app.include_router(content.router, tags=["content"])
    app.include_router(maintenance.router, tags=["maintenance"])
    app.include_router(events.router, tags=["events"])
    app.include_router(codegarden.router, tags=["codegarden"])
    app.include_router(codegarden_phase2b.router, tags=["codegarden-phase2b"])
    app.include_router(tags.router, tags=["tags"])
    app.include_router(extract.router, tags=["extract"])
    app.include_router(reviews.router, tags=["reviews"])
    app.include_router(annotations_api.router, tags=["annotations"])
    app.include_router(tech_stack.router, tags=["tech-stack"])
    app.include_router(alerts.router, tags=["alerts"])
    app.include_router(search.router, tags=["search"])
    app.include_router(mode.router, tags=["mode"])
    app.include_router(recommend.router, tags=["recommend"])
    app.include_router(digests.router, tags=["digests"])


__all__ = ["register_routers"]

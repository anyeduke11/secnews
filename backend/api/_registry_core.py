"""_registry_core.py — 路由注册表 core 无条件区 (DEV-0287 D5 拆分)。

R3 行数守卫: 原 _registry.py 291>271 (DEV-0280 注册增长) — 按域分组拆:
本文件 = core 无条件注册区 (hotspots→attention); feature flag 接线区
→ ``_registry_flags.py``; SecNews/DSH/skill_registry/v1 端到端区 →
``_registry_extensions.py``。``_registry.register_all`` 语义逐字不变
(调用顺序 = 原文件顺序, URL/method 零变更)。
"""
from __future__ import annotations

from fastapi import FastAPI


def register_core(app: FastAPI) -> None:
    """core 无条件注册区 (原 _registry.py L24-L148 的无条件段, 保序)。"""
    import backend.api.attention_events_api as attention_events_api  # v1.7: 注意力事件追踪
    from backend.api import (
        cache,  # v1.9: 缓存管理 (clear/stats)
        categories,
        codegarden,  # v1.5+: CodeGarden 代码花园 (Phase 2a)
        codegarden_ops,  # v1.5+: CodeGarden 运维层 — 服务网格/资源中枢/联动引擎 (原 phase2b)
        compliance,  # v0.6 Phase 4 S4-4: 合规矩阵 (等保 2.0 + GDPR + ISO 27001)
        content,  # v1.4: 内容创作 (calendar/drafts/templates)
        cve_analytics,  # v0.6 Phase 4 S4-3: CVE 热力图 + ATT&CK 映射
        deep_read,  # v0.6 Phase 4 S4-2: DeepRead 4 节深度分析
        events,  # v1.3.0 Phase 6: SSE 实时推送
        export,
        favorites,
        health,
        health_stats,  # Batch 2: /api/stats 自 health.py 拆出 (URL 不变)
        history,
        hotspots,
        knowledge,  # v1.4: 知识库
        knowledge_chunks_api,  # Phase 17: 知识库 chunks
        maintenance,  # v1.4: DB 维护 (vacuum/cleanup)
        mcp_settings_api,  # MCP 设置端点 (ungated, 解 extensions.mcp 自锁; P2 Task 10)
        mode,  # v1.7 Phase 3: 模式切换 (brief/scan/deep/...)
        proxy,
        quality,
        refresh,  # Phase 32: POST /api/refresh 手动触发采集
        reports,  # v1.9 Editorial: 日报/月报独立 API
        secrets,  # Phase 41: 密钥管理 (LLM API Keys)
        security,  # Phase 2: Security Knowledge Graph + Terminology
        settings,  # 运行时设置 (刷新间隔等)
        settings_flags_api,  # 能力开关读写 (feature-gates, ungated 基础设施; P2 Task 11)
        skills,  # Phase 41: Skill 管理
        sources,
        sync,  # Phase 42: 跨端配置同步 (WebDAV)
        todos,  # Phase 36: /api/todos 待办 (Todos) CRUD
        trends,
        weekly_report,  # v1.3.0 Phase 4: 周报
    )
    from backend.extensions import is_extension_enabled

    app.include_router(hotspots.router, tags=["hotspots"])
    app.include_router(trends.router, tags=["trends"])
    app.include_router(categories.router, tags=["categories"])
    app.include_router(health.router, tags=["health"])
    app.include_router(health_stats.router, tags=["health"])
    app.include_router(export.router, tags=["export"])
    app.include_router(proxy.router, tags=["proxy"])
    app.include_router(quality.router, tags=["quality"])
    # DEV-0287 (D5): quality 拒绝统计/信源信誉查询面 (原 quality.py 内, 拆分挂载)
    from backend.api import quality_rejection_api
    app.include_router(quality_rejection_api.router, tags=["quality"])
    app.include_router(sources.router, tags=["sources"])
    app.include_router(favorites.router, tags=["favorites"])
    app.include_router(history.router, tags=["history"])
    app.include_router(refresh.router, tags=["refresh"])
    app.include_router(todos.router, tags=["todos"])
    app.include_router(skills.router, tags=["skills"])
    app.include_router(secrets.router, tags=["secrets"])
    app.include_router(security.router, tags=["security"])
    app.include_router(settings.router, tags=["settings"])
    app.include_router(mcp_settings_api.router, tags=["mcp-settings"])  # ungated: extensions.mcp=false 仍可达
    app.include_router(settings_flags_api.router, tags=["feature-gates"])  # ungated: gate 管理面自身不受 gate 限制
    if is_extension_enabled("sync"):
        app.include_router(sync.router, tags=["sync"])
    app.include_router(reports.router, tags=["reports"])
    app.include_router(weekly_report.router, tags=["weekly-report"])
    app.include_router(deep_read.router, tags=["deep-read"])
    app.include_router(cve_analytics.router, tags=["cve-analytics"])
    app.include_router(compliance.router, tags=["compliance"])
    app.include_router(knowledge.router, tags=["knowledge"])
    app.include_router(knowledge_chunks_api.router, tags=["knowledge-chunks"])
    app.include_router(content.router, tags=["content"])
    app.include_router(maintenance.router, tags=["maintenance"])
    app.include_router(cache.router, tags=["cache"])
    app.include_router(events.router, tags=["events"])
    app.include_router(attention_events_api.router, tags=["attention"])
    # ---- extension 路由区: 按 feature_gates 注册 (v0.4.3 分层) ----
    if is_extension_enabled("codegarden"):
        app.include_router(codegarden.router, tags=["codegarden"])
    if is_extension_enabled("codegarden_phase2b"):
        # D5 Batch ⑧: M2/M3/M4 服务网格/资源中枢/编排引擎 — 独立 gate,
        # 之前错绑 codegarden 导致 phase2b=false 时路由仍在 (job 不跑但端点 200)
        app.include_router(codegarden_ops.router, tags=["codegarden-ops"])
    app.include_router(mode.router, tags=["mode"])


__all__ = ["register_core"]

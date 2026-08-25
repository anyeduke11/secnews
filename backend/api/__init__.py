"""Phase 4 API routers.

- :func:`register_routers` 把 7 个 APIRouter 一次性注册到 FastAPI app

每个 router 文件不超过 150 行；这里的导入是 lazy 的（不在模块级
触发 import，避免 import 循环）。
"""
from __future__ import annotations

from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    """注册全部 APIRouter (v1.7+: 含 tags + extract)。

    v1.8 加固: config.feature_* flag 在此接线 —— flag=False 的功能
    router 不注册, 对外不可达 (此前 flag 与注册脱钩, 形同虚设)。
    """
    from backend.config import config
    from backend.extensions import is_extension_enabled

    # 注意: annotations 必须用 `import ... as` 显式导入子模块,
    # 因为模块顶部的 `from __future__ import annotations` 会把 `annotations`
    # 绑定为 _Feature 实例, 导致 `from backend.api import annotations` 拿到 _Feature 而非子模块.
    import backend.api.annotations as annotations_api  # v1.7 Phase 2: 笔记空间
    import backend.api.kl_compounding_api as kl_compounding_api  # Phase 13: 复利仪表盘
    import backend.api.kl_planning_api as kl_planning_api  # Phase 13: 规划动作 API
    from backend.api import (
        bid_alert,  # Phase 4: 标书提醒与竞品分析
        cache,  # v1.9: 缓存管理 (clear/stats)
        attention_events_api,  # v1.7: 注意力事件追踪
        reports,  # v1.9 Editorial: 日报/月报独立 API
        alert_api as alert_api_v2,  # Phase 12: 告警系统 v2
        alerts,  # v1.7 Phase 3: 告警规则与告警
        knowledge_imported,  # v1.8 Phase 8: 资讯收藏聚合视图
        categories,
        crm_customers_api,  # v0.6: CRM 业绩座舱 — 客户 CRUD
        crm_opportunities_api,  # v0.6: CRM 业绩座舱 — 商机状态机
        crm_stats_api,  # v0.6: CRM 业绩座舱 — KPI/图表聚合
        catchup,  # v1.8 Phase 8: 追抓资讯 (manual + watchdog auto)
        digests,  # v1.7 Phase 4: 简报
        mode,  # v1.7 Phase 3: 模式切换 (brief/scan/deep/...)
        recommend,  # v1.7 Phase 4: 上下文推荐
        search,  # v1.7 Phase 3: 统一跨层搜索
        codegarden,  # v1.5+: CodeGarden 代码花园 (Phase 2a)
        codegarden_ops,  # v1.5+: CodeGarden 运维层 — 服务网格/资源中枢/联动引擎 (原 phase2b)
        content,  # v1.4: 内容创作 (calendar/drafts/templates)
        events,  # v1.3.0 Phase 6: SSE 实时推送
        export,
        extract,  # v1.7 Phase 1: 标签自动提取
        favorites,
        health,
        history,
        hotspots,
        knowledge,  # v1.4: 知识库
        knowledge_chunks_api,  # Phase 17: 知识库 chunks
        maintenance,  # v1.4: DB 维护 (vacuum/cleanup)
        mcp,  # v1.7 Phase 7: MCP 调试端点 (/api/mcp/* + /api/settings/mcp/*)
        mcp_adapters,  # v1.7 Phase 7: MCP 适配端点 (/api/profile, /api/cubox/sync, /api/extract/auto)
        mcp_agent_tools,  # v1.8: 4 个 Agent 侧写 tool (score_item/enrich_concept/link_items/trigger_codegarden_drift)
        kl_metrics_api,  # v1.7 Phase 10: KL 触发器指标 (/api/kl/metrics)
        kl_rollback_api,  # v1.7 Phase 10: KL 回滚 API (/api/kl/rollback)
        proxy,
        quality,
        refresh,  # Phase 32: POST /api/refresh 手动触发采集
        reviews,  # v1.7 Phase 2: SM-2 间隔复习
        secrets,  # Phase 41: 密钥管理 (LLM API Keys)
        security,  # Phase 2: Security Knowledge Graph + Terminology
        settings,  # 运行时设置 (刷新间隔等)
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
    app.include_router(settings.router, tags=["settings"])
    if is_extension_enabled("sync"):
        app.include_router(sync.router, tags=["sync"])
    app.include_router(reports.router, tags=["reports"])
    app.include_router(weekly_report.router, tags=["weekly-report"])
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
        app.include_router(codegarden_ops.router, tags=["codegarden-ops"])
    if is_extension_enabled("crm"):
        app.include_router(crm_customers_api.router, tags=["crm"])
        app.include_router(crm_opportunities_api.router, tags=["crm"])
        app.include_router(crm_stats_api.router, tags=["crm"])
    # ---- feature flag 接线区: flag=False 时对应 API 不注册 ----
    if config.feature_tag:
        app.include_router(tags.router, tags=["tags"])
    if config.feature_auto_extract:
        app.include_router(extract.router, tags=["extract"])
    if config.feature_review:
        app.include_router(reviews.router, tags=["review"])
    if config.feature_annotation:
        app.include_router(annotations_api.router, tags=["annotation"])
    if config.feature_tech_stack and is_extension_enabled("tech_stack"):
        app.include_router(tech_stack.router, tags=["tech-stack"])
    if config.feature_alert:
        app.include_router(alerts.router, tags=["alert"])
    # Phase 12: 告警系统 v2 (不依赖 feature flag，随 app 启动)
    app.include_router(alert_api_v2.router, tags=["alerts-v2"])
    if config.feature_unified_search:
        app.include_router(search.router, tags=["search"])
    app.include_router(mode.router, tags=["mode"])
    if config.feature_recommendation:
        app.include_router(recommend.router, tags=["recommend"])
    if config.feature_digest:
        app.include_router(digests.router, tags=["digest"])
    # v1.8 Phase 8: 追抓资讯
    app.include_router(catchup.router, tags=["catchup"])
    # v1.8 Phase 8: 资讯收藏聚合视图
    app.include_router(knowledge_imported.router, tags=["knowledge-imported"])
    # v1.7 Phase 7: MCP server routers (v0.4.3: 由 feature_gates 控制)
    if is_extension_enabled("mcp"):
        app.include_router(mcp.router, tags=["mcp"])
        app.include_router(mcp_adapters.router, tags=["mcp-adapters"])
        # v1.8 Phase 8: 4 个新 MCP tool (副作用模式)
        app.include_router(mcp_agent_tools.router, tags=["mcp-agent-tools"])
    # v1.7 Phase 10: KL 触发器指标
    app.include_router(kl_metrics_api.router, tags=["kl-metrics"])
    # v1.7 Phase 10: KL 回滚 API
    app.include_router(kl_rollback_api.router, tags=["kl"])
    # Phase 13: 复利仪表盘 API
    app.include_router(kl_compounding_api.router, tags=["kl-compounding"])
    # Phase 13: 规划动作 API
    app.include_router(kl_planning_api.router, tags=["kl-planning"])
    # v0.5 §18.4: wiki_* MCP 工具族 (llm-wiki-2.0 消费面)
    from backend.api import wiki_tools
    app.include_router(wiki_tools.router, tags=["wiki-tools"])
    # Phase 14: 子系统联动 — 技术栈漂移评估 + CVE 同步
    from backend.api import codegarden_phase14
    if is_extension_enabled("codegarden"):
        app.include_router(codegarden_phase14.router, tags=["codegarden-phase14"])
    # Phase 16: Hybrid AI — LLM 状态 API
    from backend.api import llm_status
    app.include_router(llm_status.router, tags=["llm"])
    # Phase 4: 标书提醒与竞品分析
    app.include_router(bid_alert.router, tags=["bid-alert"])
    # SecNews 整合 Phase 0: KL 管线 + 安全看板 (按 feature_gates 注册)
    if is_extension_enabled("secnews"):
        from backend.api import kl_pipeline_api, secnews_dashboard_api
        app.include_router(kl_pipeline_api.router, tags=["kl-pipeline"])
        app.include_router(secnews_dashboard_api.router, tags=["secnews"])


__all__ = ["register_routers"]

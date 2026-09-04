"""API 路由注册表 — 拆自 ``backend/api/__init__.py`` (P0-2, v0.6.2)。

原 188 行 __init__.py 拆为:

- ``__init__.py``        — 薄壳, 仅暴露 ``register_routers`` 公开 API (≤ 30 行)
- ``_registry.py`` (本文) — 实际分组与 ``app.include_router`` 调用
- ``_flags.py``           — feature_flag 批量检查, 减少 register_routers 内的 ``if config.feature_xxx`` 块

约束: 任何 ``from backend.api import register_routers`` / ``backend.api.register_routers`` 仍可解析。
"""
from __future__ import annotations

from fastapi import FastAPI


def register_all(app: FastAPI) -> None:
    """注册全部 APIRouter (v1.7+: 含 tags + extract)。

    v1.8 加固: config.feature_* flag 在此接线 —— flag=False 的功能
    router 不注册, 对外不可达 (此前 flag 与注册脱钩, 形同虚设)。
    """
    # 注意: annotations 必须用 `import ... as` 显式导入子模块,
    # 因为模块顶部的 `from __future__ import annotations` 会把 `annotations`
    # 绑定为 _Feature 实例, 导致 `from backend.api import annotations` 拿到 _Feature 而非子模块.
    import backend.api.annotations as annotations_api  # v1.7 Phase 2: 笔记空间
    import backend.api.kl_compounding_api as kl_compounding_api  # Phase 13: 复利仪表盘
    import backend.api.kl_planning_api as kl_planning_api  # Phase 13: 规划动作 API
    from backend.api import (
        alert_api as alert_api_v2,  # Phase 12: 告警系统 v2
    )
    from backend.api import (
        alerts,  # v1.7 Phase 3: 告警规则与告警
        attention_events_api,  # v1.7: 注意力事件追踪
        bid_alert,  # Phase 4: 标书提醒与竞品分析
        cache,  # v1.9: 缓存管理 (clear/stats)
        catchup,  # v1.8 Phase 8: 追抓资讯 (manual + watchdog auto)
        categories,
        codegarden,  # v1.5+: CodeGarden 代码花园 (Phase 2a)
        codegarden_ops,  # v1.5+: CodeGarden 运维层 — 服务网格/资源中枢/联动引擎 (原 phase2b)
        compliance,  # v0.6 Phase 4 S4-4: 合规矩阵 (等保 2.0 + GDPR + ISO 27001)
        content,  # v1.4: 内容创作 (calendar/drafts/templates)
        crm_customers_api,  # v0.6: CRM 业绩座舱 — 客户 CRUD
        crm_opportunities_api,  # v0.6: CRM 业绩座舱 — 商机状态机
        crm_stats_api,  # v0.6: CRM 业绩座舱 — KPI/图表聚合
        cve_analytics,  # v0.6 Phase 4 S4-3: CVE 热力图 + ATT&CK 映射
        deep_read,  # v0.6 Phase 4 S4-2: DeepRead 4 节深度分析
        digests,  # v1.7 Phase 4: 简报
        events,  # v1.3.0 Phase 6: SSE 实时推送
        export,
        extract,  # v1.7 Phase 1: 标签自动提取
        favorites,
        health,
        history,
        hotspots,
        kl_metrics_api,  # v1.7 Phase 10: KL 触发器指标 (/api/kl/metrics)
        kl_rollback_api,  # v1.7 Phase 10: KL 回滚 API (/api/kl/rollback)
        knowledge,  # v1.4: 知识库
        knowledge_chunks_api,  # Phase 17: 知识库 chunks
        knowledge_imported,  # v1.8 Phase 8: 资讯收藏聚合视图
        maintenance,  # v1.4: DB 维护 (vacuum/cleanup)
        mcp,  # v1.7 Phase 7: MCP 调试端点 (/api/mcp/* + /api/settings/mcp/*)
        mcp_adapters,  # v1.7 Phase 7: MCP 适配端点 (/api/profile, /api/cubox/sync, /api/extract/auto)
        mcp_agent_tools,  # v1.8: 4 个 Agent 侧写 tool (score_item/enrich_concept/link_items/trigger_codegarden_drift)
        mode,  # v1.7 Phase 3: 模式切换 (brief/scan/deep/...)
        proxy,
        quality,
        recommend,  # v1.7 Phase 4: 上下文推荐
        refresh,  # Phase 32: POST /api/refresh 手动触发采集
        reports,  # v1.9 Editorial: 日报/月报独立 API
        reviews,  # v1.7 Phase 2: SM-2 间隔复习
        search,  # v1.7 Phase 3: 统一跨层搜索
        secrets,  # Phase 41: 密钥管理 (LLM API Keys)
        security,  # Phase 2: Security Knowledge Graph + Terminology
        settings,  # 运行时设置 (刷新间隔等)
        skills,  # Phase 41: Skill 管理
        sources,
        sync,  # Phase 42: 跨端配置同步 (WebDAV)
        tags,  # v1.7 Phase 1: 标签管理
        tech_stack,  # v1.7 Phase 2: 技术栈 + 项目桥接
        todos,  # Phase 36: /api/todos 待办 (Todos) CRUD
        trends,
        weekly_report,  # v1.3.0 Phase 4: 周报
    )
    from backend.config import config
    from backend.extensions import is_extension_enabled

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
        # v0.6 Phase 5 commit 3: 5 个 MCP tool 扩展 (kl_*/dsh_*)
        from backend.api import mcp_phase5_tools
        app.include_router(mcp_phase5_tools.kl_router, tags=["mcp-kl-tools"])
        app.include_router(mcp_phase5_tools.dsh_router, tags=["mcp-dsh-tools"])
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
    # D5 Batch ⑧: phase14 是 M4 联动引擎, 跟随 codegarden_phase2b gate
    from backend.api import codegarden_phase14
    if is_extension_enabled("codegarden_phase2b"):
        app.include_router(codegarden_phase14.router, tags=["codegarden-phase14"])
    # Phase 16: Hybrid AI — LLM 状态 API
    from backend.api import llm_status
    app.include_router(llm_status.router, tags=["llm"])
    # v0.7.4-image: 图片生成 + 图理解 (复用 Batch ⑥ 凭据链, sensenova u1.5-lite)
    from backend.api import image
    app.include_router(image.router, tags=["image"])
    # v0.7 Batch ③: 观测面 query API (无条件注册, 是基础设施)
    from backend.api import observability_router
    app.include_router(observability_router.router, tags=["observability"])
    # Phase 4: 标书提醒与竞品分析
    app.include_router(bid_alert.router, tags=["bid-alert"])
    # SecNews 整合 Phase 0: KL 管线 + 安全看板 (按 feature_gates 注册)
    if is_extension_enabled("secnews"):
        from backend.api import feedback_api, kl_pipeline_api, secnews_dashboard_api
        app.include_router(feedback_api.router, tags=["feedback"])
        app.include_router(kl_pipeline_api.router, tags=["kl-pipeline"])
        app.include_router(secnews_dashboard_api.router, tags=["secnews"])
    # v0.6 P0: DSH 桥接层 (按 feature_gates 注册)
    # v0.6.3: 内置化 — dsh 升级为受管子进程 (control 面启停), pi 执行 agent 同 gate
    if is_extension_enabled("dsh"):
        from backend.api import dsh_api
        app.include_router(dsh_api.router, tags=["dsh"])
        from backend.api import dsh_control_api
        app.include_router(dsh_control_api.router, tags=["dsh-control"])
        from backend.api import agents_api
        app.include_router(agents_api.router, tags=["agents"])
    # v0.8 P1 info_filter: 独立资讯筛选门禁
    if is_extension_enabled("info_filter"):
        from backend.api import info_filter_api
        app.include_router(info_filter_api.router, tags=["info-filter"])
    # v0.8 Phase A A3: skill_registry Skill 商店 (默认 false, 开闸归 A5)
    if is_extension_enabled("skill_registry"):
        from backend.api import skill_registry_api
        app.include_router(skill_registry_api.router, tags=["skill-registry"])
        # v0.8 Phase B B6: 运行历史 + 反馈打分 (与 A3 同 gate, 拆文件避 150 行上限)
        from backend.api import skill_registry_runs_api
        app.include_router(skill_registry_runs_api.router, tags=["skill-registry"])
    # v0.8 Phase C C3: Skill Builder (用户自建 skill)
    if is_extension_enabled("user_skills"):
        from backend.api import skill_builder_api
        app.include_router(skill_builder_api.router, tags=["skill-builder"])
    # v0.8 Phase D D1: webhook + KL + collector 触发源适配 (webhook 端点需暴露, 沿用 trigger_gate gate)
    if is_extension_enabled("trigger_gate"):
        from backend.api import trigger_webhook_api
        app.include_router(trigger_webhook_api.router, tags=["trigger-webhook"])


__all__ = ["register_all"]

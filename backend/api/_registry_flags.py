"""_registry_flags.py — feature flag 接线区 (DEV-0287 D5 二次拆分)。

R3 行数守卫: _registry_core.py 190>150 — core 无条件注册区与 feature flag
接线区再分半。本文件承载 ``config.feature_*`` 门控路由 (tags/extract/
review/annotation/tech_stack/alert/search/recommend/digest + 告警 v2 注册序
契约 + MCP server 族 + wiki 工具 + LLM/image/observability/ops_runs)。
调用顺序 = 原 _registry.py 顺序 (告警 v2 先于 v1 的注册序契约原样保留)。
"""
from __future__ import annotations

from fastapi import FastAPI


def register_flags(app: FastAPI) -> None:
    """feature flag 接线区 (原 _registry_core.py L117-L196 逐字搬移)。"""
    import backend.api.annotations as annotations_api  # v1.7 Phase 2: 笔记空间
    import backend.api.kl_compounding_api as kl_compounding_api  # Phase 13: 复利仪表盘
    import backend.api.kl_planning_api as kl_planning_api  # Phase 13: 规划动作 API
    from backend.api import (
        alert_api as alert_api_v2,  # Phase 12: 告警系统 v2
    )
    from backend.api import (
        alerts,  # v1.7 Phase 3: 告警规则与告警
        catchup,  # v1.8 Phase 8: 追抓资讯 (manual + watchdog auto)
        digests,  # v1.7 Phase 4: 简报
        extract,  # v1.7 Phase 1: 标签自动提取
        kl_metrics_api,  # v1.7 Phase 10: KL 触发器指标 (/api/kl/metrics)
        kl_rollback_api,  # v1.7 Phase 10: KL 回滚 API (/api/kl/rollback)
        knowledge_imported,  # v1.8 Phase 8: 资讯收藏聚合视图
        mcp,  # v1.7 Phase 7: MCP 调试端点 (/api/mcp/*)
        mcp_adapters,  # v1.7 Phase 7: MCP 适配端点
        mcp_agent_tools,  # v1.8: 4 个 Agent 侧写 tool
        recommend,  # v1.7 Phase 4: 上下文推荐
        reviews,  # v1.7 Phase 2: SM-2 间隔复习 + migration 120 管理面
        reviews_manage,
        search,  # v1.7 Phase 3: 统一跨层搜索
        tags,  # v1.7 Phase 1: 标签管理
        tech_stack,  # v1.7 Phase 2: 技术栈 + 项目桥接
    )
    from backend.config import config
    from backend.extensions import is_extension_enabled

    if config.feature_tag:
        app.include_router(tags.router, tags=["tags"])
    if config.feature_auto_extract:
        app.include_router(extract.router, tags=["extract"])
    if config.feature_review:
        app.include_router(reviews.router, tags=["review"])
        # migration 120: 管理面端点 (forecast/undo/PATCH/DELETE/history/cards)
        app.include_router(reviews_manage.router, tags=["review"])
    if config.feature_annotation:
        app.include_router(annotations_api.router, tags=["annotation"])
    if config.feature_tech_stack and is_extension_enabled("tech_stack"):
        app.include_router(tech_stack.router, tags=["tech-stack"])
    # Phase 12: 告警系统 v2 (不依赖 feature flag，随 app 启动)
    # 注册序契约: v2 必须先于 v1 注册 — 否则 GET /api/alerts/v2 被 v1 的
    # GET /api/alerts/{alert_id} 捕获 ("v2" 当 alert_id → 404), 首页告警列表恒空
    # (2026-10-01 实弹揪出; 同款契约先例: hotspots.py /picked 先于 /{item_id})
    app.include_router(alert_api_v2.router, tags=["alerts-v2"])
    if config.feature_alert:
        app.include_router(alerts.router, tags=["alert"])
    if config.feature_unified_search:
        app.include_router(search.router, tags=["search"])
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
    # Phase 14: 子系统联动 — 跟随 codegarden_phase2b gate (D5 Batch ⑧: M4 联动引擎)
    from backend.api import codegarden_phase14
    if is_extension_enabled("codegarden_phase2b"):
        app.include_router(codegarden_phase14.router, tags=["codegarden-phase14"])
    # Phase 16: Hybrid AI — LLM 状态 API
    from backend.api import llm_status
    app.include_router(llm_status.router, tags=["llm"])
    # DEV-0244: LLM 模型池 (内置平台目录 + /models 探测; pi Agent 单列不在此)
    from backend.api import llm_pool_api
    app.include_router(llm_pool_api.router, tags=["llm-pool"])
    # v0.7.4-image: 图片生成 + 图理解 (复用 Batch ⑥ 凭据链, sensenova u1.5-lite)
    from backend.api import image
    app.include_router(image.router, tags=["image"])
    # v0.7 Batch ③: 观测面 query API (无条件注册, 是基础设施)
    from backend.api import observability_router
    app.include_router(observability_router.router, tags=["observability"])
    # v0.8.6 P0-5 (M5 最小版): 统一 run record 查询 — job 失败/错过 UI 可查
    from backend.api import ops_runs_api
    app.include_router(ops_runs_api.router, tags=["ops"])
    # DEV-0287 (D5): 拆分半区聚合挂载 (URL 零变更)
    from backend.api import knowledge_classify_api  # knowledge_import 分类面拆出
    app.include_router(knowledge_classify_api.router, tags=["knowledge"])
    from backend.api import quality_rules_dry_run_api  # quality_rules dry-run 拆出
    app.include_router(quality_rules_dry_run_api.router, tags=["quality"])


__all__ = ["register_flags"]

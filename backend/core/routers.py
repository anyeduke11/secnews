"""Core 管道路由器白名单 — 永远注册，不受扩展开关影响。

模块名对应 ``backend.api`` 下的 router 模块（含 annotations/alert_api
别名，不含 mcp_config/mcp_types/middleware 等非 router 模块）。

v0.8.6 P0-8 (审计 E11, 2026-10-02) 白名单语义重组:
- ``CORE_ROUTERS``      = ``_registry.py`` 中**无条件** include_router 的模块
  (此前 45 项中 8 项实为 ``config.feature_*`` 条件注册 — 白名单在撒谎;
  另有 23 个无条件注册模块漏登记 — 完整性从无断言)。
- ``CONDITIONAL_ROUTERS`` = core 域但按 ``config.feature_*`` flag 条件注册
  的模块 (v1.8 flag 接线: flag=False 时不注册)。
- ``backend/extensions.EXTENSION_ROUTERS`` = 按 ``is_extension_enabled``
  (feature_gates.toml) 条件注册的扩展域模块 (不在本文件)。

完整性由 ``backend/tests/test_core_routers_completeness.py`` AST 静态核对:
_registry.py 实际注册面必须与三张表逐一对上, 新增 router 漏登记即 CI 红。
"""
from __future__ import annotations

from backend.extensions import EXTENSION_ROUTERS

# 无条件注册 (register_all 顶层 include_router) — 启动即注册, 不受任何开关影响
CORE_ROUTERS: frozenset[str] = frozenset({
    # 采集管道
    "hotspots", "trends", "categories", "sources", "health",
    "health_stats",  # Batch 2: /api/stats 自 health.py 拆出 (P0-8 补登记)
    "export", "proxy", "quality", "refresh", "catchup",
    # 知识库
    "knowledge", "knowledge_chunks_api", "knowledge_imported",
    "mode",
    # 深读/图谱/合规 (v0.6 Phase 4; P0-8 补登记)
    "deep_read", "cve_analytics", "compliance",
    # 行动层
    # DEV-0178: "bid_alert" 已随标讯剔除移除 (core 白名单同步)
    "content", "todos", "secrets", "skills",
    "reports", "weekly_report", "maintenance",
    # 复利引擎 (kl_* core 域)
    "kl_compounding_api", "kl_metrics_api", "kl_rollback_api", "kl_planning_api",
    "attention_events_api",
    # 系统
    "settings", "cache", "events", "favorites", "history", "security",
    "alert_api",  # Phase 12 告警 v2 (无条件; v1 alerts 在 CONDITIONAL)
    "llm_status",
    "llm_pool_api",  # DEV-0244: LLM 模型池 (P0-8 补登记)
    "image",  # v0.7.4-image 图片生成/图理解 (P0-8 补登记)
    # 存量 bug 清扫 C4: 以下模块在 _registry.py 无条件注册 (事实 core),
    # 但此前未登记白名单 → 防漂移覆盖不完整
    "wiki_tools", "observability_router",
    # v0.8.6 P0-5: 统一 run record 查询 (基础设施, 无条件注册)
    "ops_runs_api",
    # ungated 基础设施 (gate 管理面自身不受 gate 限制; P0-8 补登记)
    "mcp_settings_api", "settings_flags_api",
    # v1.0 端到端 API (T08-T18/C13/MP-2 等, 无 gate 限制; P0-8 补登记)
    "case_api", "judgment_api", "action_api", "run_api", "artifact_api",
    "run_ledger_api",  # v0.8.6 P1-1: proposal 审批 + Run 账本
    "command_bar_api",  # v0.8.6 P1-4: M4 命令栏
    "quality_api",  # v0.8.6 P1-5: 拒收回放
    "knowledge_api",
    "observability_audit_api",
    "legacy_migrate_api", "legacy_items_migrate_api", "legacy_migrate_v1_api",
    "v1_signals_api",
    "event_technique_api", "event_types_api",
    "cubox_import_api", "auto_intake_api",
})

# core 域但按 config.feature_* flag 条件注册 (flag=False 时不注册, v1.8 接线)
CONDITIONAL_ROUTERS: frozenset[str] = frozenset({
    "tags",           # config.feature_tag
    "extract",        # config.feature_auto_extract
    "reviews",        # config.feature_review (+ reviews_manage 同 flag)
    "reviews_manage",
    "annotations",    # config.feature_annotation
    "alerts",         # config.feature_alert (v1; v2 alert_api 无条件在 CORE)
    "search",         # config.feature_unified_search
    "recommend",      # config.feature_recommendation
    "digests",        # config.feature_digest
})

# 防漂移断言 (P0-8 扩为三向): core / conditional / extension 三表互不重叠,
# 程序员错误时 import 即炸。完整性 (漏登记) 由
# backend/tests/test_core_routers_completeness.py AST 核对。
_EXT_MODULES = {m for mods in EXTENSION_ROUTERS.values() for m in mods}
_overlap = (CORE_ROUTERS | CONDITIONAL_ROUTERS) & _EXT_MODULES
if _overlap:
    raise AssertionError(
        f"core/conditional/extension router overlap: {sorted(_overlap)}"
    )
_inner_overlap = CORE_ROUTERS & CONDITIONAL_ROUTERS
if _inner_overlap:
    raise AssertionError(
        f"core/conditional router overlap: {sorted(_inner_overlap)}"
    )

__all__ = ["CONDITIONAL_ROUTERS", "CORE_ROUTERS"]

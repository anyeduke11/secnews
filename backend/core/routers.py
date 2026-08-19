"""Core 管道路由器白名单 — 永远注册，不受扩展开关影响。

模块名对应 ``backend.api`` 下的 router 模块（含 annotations/alert_api
别名，不含 mcp_config/mcp_types/middleware 等非 router 模块）。
"""
from __future__ import annotations

from backend.extensions import EXTENSION_ROUTERS

CORE_ROUTERS: frozenset[str] = frozenset({
    # 采集管道
    "hotspots", "trends", "categories", "sources", "health",
    "export", "proxy", "quality", "refresh", "catchup",
    # 知识库
    "knowledge", "knowledge_chunks_api", "knowledge_imported",
    "search", "extract", "tags", "mode", "recommend",
    # 行动层
    "content", "todos", "secrets", "skills", "bid_alert",
    "reports", "weekly_report", "maintenance",
    # 复利引擎 (kl_* core 域)
    "kl_compounding_api", "kl_metrics_api", "kl_rollback_api", "kl_planning_api",
    "reviews", "attention_events_api", "annotations",
    # 系统
    "settings", "cache", "events", "favorites", "history", "security",
    "alerts", "alert_api", "digests", "llm_status",
})

# 防漂移断言: core 与扩展模块不得重叠（程序员错误时立即暴露）
_EXT_MODULES = {m for mods in EXTENSION_ROUTERS.values() for m in mods}
_overlap = CORE_ROUTERS & _EXT_MODULES
if _overlap:
    raise AssertionError(
        f"core/extension router overlap: {sorted(_overlap)}"
    )

__all__ = ["CORE_ROUTERS"]

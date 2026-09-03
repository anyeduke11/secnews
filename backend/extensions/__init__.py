"""扩展注册表 — feature_gates.toml 单一开关源。

扩展层设计原则:
- 代码完整保留（物理不搬），运行时按 ``feature_gates.toml`` 控制可见性
- false = 路由不注册 + job 不调度 + 前端 tab 隐藏
- ``_load_gates()`` 读取失败时保守回退为"全部开启"（不伤害核心管道）
- CI/测试可通过环境变量 ``HOTSPOT_FEATURE_GATES`` (JSON) 覆盖开关
"""
from __future__ import annotations

import json
import logging
import os
import tomllib
from pathlib import Path

_logger = logging.getLogger(__name__)

_GATES_PATH = Path(__file__).resolve().parent.parent / "config" / "feature_gates.toml"

# 全部扩展域名称（含无 router 的 security_graph —— 只占 job）
# P1.6: codegarden (M1 项目核心) 与 codegarden_phase2b (M2/M3/M4 服务网格等) 拆开
_EXTENSION_NAMES = (
    "codegarden", "codegarden_phase2b", "mcp", "sync",
    "tech_stack", "security_graph", "secnews", "crm",
    # dsh 桥接: _registry.py 以 is_extension_enabled("dsh") 守卫 dsh_api。
    # 此前漏登记 → feature_gates.toml 的 dsh=false 被过滤掉, 端点意外在线。
    "dsh",
    # v0.8 P1 info_filter: 独立资讯筛选门禁 (源级 allow/deny 名单, 实时启停)
    "info_filter",
)

# 扩展→router 映射（每个 router 是 backend.api 中的模块名）
# 与 backend/api/_registry.py 的 gate 分支保持一致 (存量 bug 清扫 D5 批:
# phase14 错绑 codegarden 已改 phase2b; dsh/mcp/secnews 名单补齐).
EXTENSION_ROUTERS: dict[str, list[str]] = {
    "codegarden": [
        "codegarden",           # Phase 2a 项目生命周期 (M1 核心)
    ],
    "codegarden_phase2b": [
        "codegarden_ops",       # Phase 2b 服务网格/资源中枢/联动引擎 (M2/M3/M4)
        "codegarden_phase14",   # Phase 14 子系统联动 (漂移评估 + CVE 同步) — D5 起跟随 phase2b
    ],
    "mcp": [
        "mcp",                  # MCP 调试端点 (/api/mcp/*)
        "mcp_adapters",         # MCP 适配端点 (/api/profile, /api/cubox/sync, ...)
        "mcp_agent_tools",      # 4 个 Agent 侧写 tool
        "mcp_phase5_tools",     # Phase 5 扩展 tool (kl_router + dsh_router)
    ],
    "sync": ["sync"],           # 跨端配置同步 (WebDAV)
    "tech_stack": ["tech_stack"],  # 技术栈管理 + 漂移评估
    "secnews": [                  # 安全看板 (KL 管线 + Feed + Dashboard)
        "kl_pipeline_api",
        "secnews_dashboard_api",
        "feedback_api",         # 用户反馈 (/api/feedback/*)
    ],
    "crm": [                      # CRM 业绩座舱 (security-cockpit 方案 C)
        "crm_customers_api",
        "crm_opportunities_api",
        "crm_stats_api",
    ],
    "dsh": [                      # dsh 桥接 + pi 执行 agent (此前整键缺失 →
        "dsh_api",                #  /api/settings/features enabled_extensions 漏报)
        "dsh_control_api",
        "agents_api",
    ],
    "info_filter": [              # v0.8 P1 独立资讯筛选门禁
        "info_filter_api",        #   /api/info-filter/* (CRUD + preview + gate)
    ],
    # security_graph 不占 router (security / kl_* 属 core 核心安全数据),
    # 只控制 mitre_sync / cve_sync_to_security 两个 job
}

# P1-1 (v0.6.2): 扩展→job 归属表 (与 EXTENSION_ROUTERS 并列, 单一来源).
# 此前 _JOB_EXT_MAP 散落在 backend/scheduler/scheduler.py + 测试三处重复;
# 现统一在此声明, scheduler.py 与测试反向派生.
EXTENSION_JOBS: dict[str, list[str]] = {
    "sync": ["sync"],                       # 跨端配置同步 (Mon 10:30)
    "codegarden": [
        "cg_upstream_sync",                 # 上游同步 (daily 09:00) — M1 核心
    ],
    "codegarden_phase2b": [
        "cg_service_scan",                  # 服务网格自动发现 (5min) — M2, P1.6
        "cg_event_process",                 # 事件总线处理 (60s) — M4, P1.6
    ],
    "tech_stack": [
        "cg_drift_assess",                  # 技术栈漂移评估 (3600s)
    ],
    "security_graph": [
        "mitre_sync",                       # MITRE ATT&CK 同步 (Sun 04:00)
        "cve_sync_to_security",             # CVE 同步到 security 实体 (1800s)
    ],
    "secnews": [
        "kl_pipeline_heartbeat",            # KL 管线心跳消费 (60s) — SECNEWS Phase 1
        "secnews_liveness_sweep",           # 书签存活三态批扫 (Sun 02:00 UTC) — S1-3
    ],
}

# 反向派生: job→扩展. 替代 scheduler.py 中重复的 _JOB_EXT_MAP.
JOB_TO_EXTENSION: dict[str, str] = {
    job: ext
    for ext, jobs in EXTENSION_JOBS.items()
    for job in jobs
}

# 默认关闭 (fail-closed): 新增扩展若漏登记 feature_gates.toml, 应当不注册、
# 不调度, 而不是在"全 API 无认证"的工作站上意外开放。
# 实测爆炸半径 0: 当前 9 个扩展名全部在 TOML 中显式声明。
_DEFAULT_GATES: dict[str, bool] = dict.fromkeys(_EXTENSION_NAMES, False)

_GATES_CACHE: dict[str, bool] | None = None


def _load_gates() -> dict[str, bool]:
    """读取 feature_gates.toml；失败则保持 fail-closed 默认 (全关)；env 可覆盖。"""
    global _GATES_CACHE
    if _GATES_CACHE is not None:
        return _GATES_CACHE

    gates = dict(_DEFAULT_GATES)

    try:
        with open(_GATES_PATH, "rb") as f:
            raw = tomllib.load(f).get("extensions", {})
        gates.update({k: bool(v) for k, v in raw.items() if k in _DEFAULT_GATES})
    except Exception as e:
        # 不静默: 默认已是全关, 这里只记录, 让"扩展集体消失"可被诊断而非猜测
        _logger.error(
            "feature_gates 读取失败 (%s: %s); 全部扩展按默认关闭处理",
            _GATES_PATH, e,
        )

    # CI/测试覆盖: HOTSPOT_FEATURE_GATES='{"extensions": {"codegarden": false, ...}}'
    # 优先级: 默认 < TOML < env
    env_json = os.environ.get("HOTSPOT_FEATURE_GATES")
    if env_json:
        try:
            data = json.loads(env_json)
            override = data.get("extensions", data)
            gates.update({k: bool(v) for k, v in override.items() if k in _DEFAULT_GATES})
        except json.JSONDecodeError:
            pass

    _GATES_CACHE = gates
    return _GATES_CACHE


def is_extension_enabled(name: str) -> bool:
    """扩展是否启用。未知名称按**关闭**处理 (fail-closed, 防漏登记即开放)。"""
    return bool(_load_gates().get(name, False))


def get_enabled_extensions() -> list[str]:
    """当前启用的扩展列表（按 EXTENSION_ROUTERS 顺序）。"""
    gates = _load_gates()
    return [name for name in EXTENSION_ROUTERS if gates.get(name, False)]


def get_extension_routers(name: str) -> list[str]:
    """扩展对应的 backend.api 模块名列表。"""
    return EXTENSION_ROUTERS.get(name, [])


def get_extension_jobs(name: str) -> list[str]:
    """P1-1: 扩展对应的 scheduler job 列表。"""
    return EXTENSION_JOBS.get(name, [])


def reset_gates() -> None:
    """清空缓存强制重读（测试用）。"""
    global _GATES_CACHE
    _GATES_CACHE = None


__all__ = [
    "EXTENSION_JOBS",
    "EXTENSION_ROUTERS",
    "JOB_TO_EXTENSION",
    "get_enabled_extensions",
    "get_extension_jobs",
    "get_extension_routers",
    "is_extension_enabled",
    "reset_gates",
]

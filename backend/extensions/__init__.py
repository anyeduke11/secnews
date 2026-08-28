"""扩展注册表 — feature_gates.toml 单一开关源。

扩展层设计原则:
- 代码完整保留（物理不搬），运行时按 ``feature_gates.toml`` 控制可见性
- false = 路由不注册 + job 不调度 + 前端 tab 隐藏
- ``_load_gates()`` 读取失败时保守回退为"全部开启"（不伤害核心管道）
- CI/测试可通过环境变量 ``HOTSPOT_FEATURE_GATES`` (JSON) 覆盖开关
"""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

_GATES_PATH = Path(__file__).resolve().parent.parent / "config" / "feature_gates.toml"

# 全部扩展域名称（含无 router 的 security_graph —— 只占 job）
# P1.6: codegarden (M1 项目核心) 与 codegarden_phase2b (M2/M3/M4 服务网格等) 拆开
_EXTENSION_NAMES = (
    "codegarden", "codegarden_phase2b", "mcp", "sync",
    "tech_stack", "security_graph", "secnews", "crm",
)

# 扩展→router 映射（每个 router 是 backend.api 中的模块名）
EXTENSION_ROUTERS: dict[str, list[str]] = {
    "codegarden": [
        "codegarden",           # Phase 2a 项目生命周期 (M1 核心)
        "codegarden_phase14",   # Phase 14 子系统联动 (漂移评估 + CVE 同步)
    ],
    "codegarden_phase2b": [
        "codegarden_ops",       # Phase 2b 服务网格/资源中枢/联动引擎 (M2/M3/M4)
    ],
    "mcp": [
        "mcp",                  # MCP 调试端点 (/api/mcp/*)
        "mcp_adapters",         # MCP 适配端点 (/api/profile, /api/cubox/sync, ...)
        "mcp_agent_tools",      # 4 个 Agent 侧写 tool
    ],
    "sync": ["sync"],           # 跨端配置同步 (WebDAV)
    "tech_stack": ["tech_stack"],  # 技术栈管理 + 漂移评估
    "secnews": [                  # 安全看板 (KL 管线 + Feed + Dashboard)
        "kl_pipeline_api",
        "secnews_dashboard_api",
    ],
    "crm": [                      # CRM 业绩座舱 (security-cockpit 方案 C)
        "crm_customers_api",
        "crm_opportunities_api",
        "crm_stats_api",
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

_DEFAULT_GATES: dict[str, bool] = dict.fromkeys(_EXTENSION_NAMES, True)

_GATES_CACHE: dict[str, bool] | None = None


def _load_gates() -> dict[str, bool]:
    """读取 feature_gates.toml；失败回退全部开启；env 可覆盖。"""
    global _GATES_CACHE
    if _GATES_CACHE is not None:
        return _GATES_CACHE

    gates = dict(_DEFAULT_GATES)

    try:
        with open(_GATES_PATH, "rb") as f:
            raw = tomllib.load(f).get("extensions", {})
        gates.update({k: bool(v) for k, v in raw.items() if k in _DEFAULT_GATES})
    except Exception:
        pass  # 保守降级: 文件缺失/损坏时保持默认, 不阻塞启动

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
    """扩展是否启用。未知名称默认视为启用（核心行为不受影响）。"""
    return bool(_load_gates().get(name, True))


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
    "EXTENSION_ROUTERS",
    "EXTENSION_JOBS",
    "JOB_TO_EXTENSION",
    "get_enabled_extensions",
    "get_extension_jobs",
    "get_extension_routers",
    "is_extension_enabled",
    "reset_gates",
]

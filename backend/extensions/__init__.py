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
_EXTENSION_NAMES = ("codegarden", "mcp", "sync", "tech_stack", "security_graph")

# 扩展→router 映射（每个 router 是 backend.api 中的模块名）
EXTENSION_ROUTERS: dict[str, list[str]] = {
    "codegarden": [
        "codegarden",           # Phase 2a 项目生命周期
        "codegarden_ops",       # Phase 2b 服务网格/资源中枢/联动引擎
        "codegarden_phase14",   # Phase 14 子系统联动 (漂移评估 + CVE 同步)
    ],
    "mcp": [
        "mcp",                  # MCP 调试端点 (/api/mcp/*)
        "mcp_adapters",         # MCP 适配端点 (/api/profile, /api/cubox/sync, ...)
        "mcp_agent_tools",      # 4 个 Agent 侧写 tool
    ],
    "sync": ["sync"],           # 跨端配置同步 (WebDAV)
    "tech_stack": ["tech_stack"],  # 技术栈管理 + 漂移评估
    # security_graph 不占 router (security / kl_* 属 core 核心安全数据),
    # 只控制 mitre_sync / cve_sync_to_security 两个 job
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


def reset_gates() -> None:
    """清空缓存强制重读（测试用）。"""
    global _GATES_CACHE
    _GATES_CACHE = None


__all__ = [
    "EXTENSION_ROUTERS",
    "get_enabled_extensions",
    "get_extension_routers",
    "is_extension_enabled",
    "reset_gates",
]

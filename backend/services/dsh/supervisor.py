"""dsh 内置受管服务 — 认知大脑的生命周期与配置持久化 (v0.6.3)。

三层架构裁决 (2026-08-24): DeepSeek Harness (dsh) = 大脑。本模块把 dsh
从"外部手工拉起的进程"升级为 **hotspot 内置受管子进程**:

- 配置持久化: ``settings`` 表 KV (``dsh.endpoint`` / ``dsh.command`` /
  ``dsh.autostart``), 经 /api/dsh/control/config 可从前端写
- 生命周期: start / stop / restart (ProcessSupervisor 承载), 前端一键启停
- 健康探测: endpoint TCP/HTTP 探测 + 监督器状态合并

职责边界: 本模块不做任务派发 (task_router.py) / 会话 (session.py) /
HTTP 客户端 (bridge.py) — 只管"进程活着没有"和"配置是什么"。
"""
from __future__ import annotations

import os
import shlex
from typing import Any

from backend.logging_config import logger
from backend.repository.settings_repo import SettingsRepository
from backend.services.dsh.bridge import DSHClient
from backend.services.process_supervisor import ProcessSupervisor

_SETTINGS_PREFIX = "dsh."
_SUPERVISED_NAME = "dsh"

# 模块级单例 — hotspot 单进程架构下与 scheduler/app.state 生命周期一致
supervisor = ProcessSupervisor(max_restarts=3)


# ---------------------------------------------------------------------------
# 配置 (settings KV 持久化; env 仅作首次默认)
# ---------------------------------------------------------------------------
def _parse_command(raw: str | None) -> list[str]:
    """把 settings 里的命令字符串解析为 argv; 空串/None → []。"""
    if not raw or not raw.strip():
        return []
    try:
        return shlex.split(raw.strip())
    except ValueError as e:
        logger.warning("dsh command parse failed (%s): %s", raw, e)
        return []


def get_dsh_config() -> dict[str, Any]:
    """读 dsh 配置 (settings KV 优先, env 作 endpoint 兜底默认)。"""
    repo = SettingsRepository()
    endpoint = repo.get(f"{_SETTINGS_PREFIX}endpoint")
    if not endpoint:
        endpoint = os.getenv("DSH_ENDPOINT", "http://localhost:3210")
    command_raw = repo.get(f"{_SETTINGS_PREFIX}command", "")
    autostart = bool(repo.get(f"{_SETTINGS_PREFIX}autostart", False))
    return {
        "endpoint": endpoint,
        "command": _parse_command(command_raw),
        "command_raw": command_raw or "",
        "autostart": autostart,
    }


def set_dsh_config(
    *,
    endpoint: str | None = None,
    command: str | None = None,
    autostart: bool | None = None,
) -> dict[str, Any]:
    """写 dsh 配置并返回合并后的新配置。endpoint 空串 = 恢复 env 默认。"""
    repo = SettingsRepository()
    if endpoint is not None:
        repo.set(f"{_SETTINGS_PREFIX}endpoint", endpoint.strip())
    if command is not None:
        repo.set(f"{_SETTINGS_PREFIX}command", command.strip())
    if autostart is not None:
        repo.set(f"{_SETTINGS_PREFIX}autostart", bool(autostart))
    return get_dsh_config()


# ---------------------------------------------------------------------------
# 生命周期
# ---------------------------------------------------------------------------
def start_dsh() -> dict[str, Any]:
    """按当前配置拉起 dsh 受管进程 (幂等)。"""
    cfg = get_dsh_config()
    if not cfg["command"]:
        return {
            "ok": False,
            "error": "dsh 启动命令未配置 — 先在设置页填写启动命令 (如 "
                     "`node /path/to/dsh/dev.mjs`)",
            "status": supervisor.status(_SUPERVISED_NAME),
        }
    snap = supervisor.start(_SUPERVISED_NAME, cfg["command"])
    # endpoint 变更即时生效 (DSHClient 每次按 settings 读端点)
    return {"ok": snap["running"], "status": snap}


def stop_dsh() -> dict[str, Any]:
    return {"ok": True, "status": supervisor.stop(_SUPERVISED_NAME)}


def restart_dsh() -> dict[str, Any]:
    cfg = get_dsh_config()
    if not cfg["command"]:
        return {"ok": False, "error": "dsh 启动命令未配置", "status": supervisor.status(_SUPERVISED_NAME)}
    snap = supervisor.restart(_SUPERVISED_NAME)
    return {"ok": snap["running"], "status": snap}


def poll_dsh() -> dict[str, Any]:
    """意外退出检测 + 有限自动重启 (供 health 端点轮询顺带执行)。"""
    cfg = get_dsh_config()
    return supervisor.poll(_SUPERVISED_NAME, command=cfg["command"] or None)


# ---------------------------------------------------------------------------
# 状态合并 (监督器 + endpoint 探测)
# ---------------------------------------------------------------------------
def _probe_endpoint(endpoint: str) -> bool:
    try:
        # P1.8: with 上下文保证 httpx.Client.close() 被调用, 避免
        # 频繁探测时连接池泄漏
        with DSHClient(endpoint=endpoint) as client:
            return client.health_check()
    except Exception:
        return False


def dsh_full_status() -> dict[str, Any]:
    """监督器状态 + endpoint 探测 + 配置, 供控制面板单次拉全。"""
    cfg = get_dsh_config()
    snap = poll_dsh()
    running = snap.get("running", False)
    endpoint_reachable = _probe_endpoint(cfg["endpoint"]) if cfg["endpoint"] else False
    if running and endpoint_reachable:
        status = "connected"
    elif running:
        status = "starting"
    elif not cfg["command"]:
        status = "not_configured"
    else:
        status = "stopped"
    return {
        "status": status,
        "endpoint": cfg["endpoint"],
        "command_raw": cfg["command_raw"],
        "autostart": cfg["autostart"],
        "configured": bool(cfg["command"]),
        "endpoint_reachable": endpoint_reachable,
        "process": snap,
    }


def autostart_if_configured() -> None:
    """app lifespan 启动钩子: autostart=true 且已配置时拉起 dsh。

    失败只 warning 不阻塞启动 (认知层缺失时业务走 LLM fallback)。
    """
    cfg = get_dsh_config()
    if not cfg["autostart"] or not cfg["command"]:
        return
    try:
        result = start_dsh()
        logger.info("dsh autostart: ok=%s", result.get("ok"))
    except Exception as e:
        logger.warning("dsh autostart failed (ignored): %s", e)


__all__ = [
    "autostart_if_configured",
    "dsh_full_status",
    "get_dsh_config",
    "poll_dsh",
    "restart_dsh",
    "set_dsh_config",
    "start_dsh",
    "stop_dsh",
    "supervisor",
]

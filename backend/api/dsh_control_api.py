"""DSH 控制面 API — 内置受管服务的一键启停与配置 (v0.6.3)。

与 dsh_api.py (task/session/health) 分文件: 注册表按 feature_gates
`dsh` gate 同步注册两者, gate 关闭时一并 404。

端点 (前缀 /api/dsh/control):
- GET  /status   监督器状态 + endpoint 探测 + 配置 (单次拉全)
- POST /start    拉起 dsh 进程 (幂等; 未配置命令时 409)
- POST /stop     终止 dsh 进程
- POST /restart  重启
- PUT  /config   写 endpoint / 启动命令 (argv[0] 白名单, 拒绝→400) / autostart
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.services.dsh import supervisor as dsh_sup

router = APIRouter(prefix="/api/dsh/control", tags=["dsh-control"])


class DshConfigUpdate(BaseModel):
    """dsh 配置更新 (None = 不修改)。"""

    endpoint: str | None = Field(None, max_length=500, description="dsh 服务端点, 空串恢复 env 默认")
    command: str | None = Field(None, max_length=2000, description="启动命令字符串 (shlex 解析), 空串清除")
    autostart: bool | None = Field(None, description="app 启动时自动拉起")


@router.get("/status")
def get_control_status() -> dict[str, Any]:
    """监督器 + 探测 + 配置合并状态。"""
    return dsh_sup.dsh_full_status()


@router.post("/start")
def start_process() -> Any:
    """拉起 dsh 受管进程 (幂等)。未配置启动命令 → 409。"""
    result = dsh_sup.start_dsh()
    if not result.get("ok") and result.get("error"):
        return JSONResponse(status_code=409, content=result)
    return result


@router.post("/stop")
def stop_process() -> dict[str, Any]:
    """终止 dsh 受管进程 (未运行时静默成功)。"""
    return dsh_sup.stop_dsh()


@router.post("/restart")
def restart_process() -> Any:
    """重启 dsh 受管进程。未配置启动命令 → 409。"""
    result = dsh_sup.restart_dsh()
    if not result.get("ok") and result.get("error"):
        return JSONResponse(status_code=409, content=result)
    return result


@router.put("/config")
def update_config(body: DshConfigUpdate) -> Any:
    """持久化 dsh 配置 (settings KV), 返回合并后的新配置与状态。

    P0-A: 命令 argv[0] 未命中白名单 → 400 (service 层 set_dsh_config 亦
    强制校验, 双层防御)。
    """
    if body.command is not None and body.command.strip():
        try:
            dsh_sup.validate_command_string(body.command)
        except dsh_sup.DshCommandNotAllowedError as e:
            return JSONResponse(
                status_code=400,
                content={"code": "E_VALIDATION", "message": str(e)},
            )
    cfg = dsh_sup.set_dsh_config(
        endpoint=body.endpoint,
        command=body.command,
        autostart=body.autostart,
    )
    return {"ok": True, "config": cfg, "status": dsh_sup.dsh_full_status()}


__all__ = ["router"]

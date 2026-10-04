"""command_bar_api.py — /api/commands: M4 命令栏端点 (v0.8.6 P1-4)。

- POST /api/commands   {text} → 本地规则意图路由执行 (恒 HTTP 200, intent/
  outcome 字段区分; 查询类带结果卡含 Source url, 行动类生成 proposal)
- GET  /api/commands   命令 run record 列表 (command_log; PRD 用例 B
  "每条命令可查" 的查询口 — /api/ops/runs 是 job_runs 专用, 不混入)

command_log 写者唯一 = CommandBarService (R2 单写者)。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.services.command_bar_service import CommandBarService

router = APIRouter(prefix="/api/commands", tags=["command-bar"])


class RunCommandBody(BaseModel):
    text: str = Field(min_length=1, max_length=500)


def _svc() -> CommandBarService:
    return CommandBarService()


@router.post("")
def run_command(body: RunCommandBody) -> dict[str, Any]:
    """执行一条命令。识别不中 → intent=unknown + 可选动作清单 (不猜)。"""
    return _svc().run_command(body.text)


@router.get("")
def list_commands(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return _svc().list_commands(limit=limit, offset=offset)


__all__ = ["router"]

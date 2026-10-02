"""LLM 模型池 API — 内置平台目录 + 密钥探测 + 一键写入路由 (DEV-0244/0245)。

- ``GET  /api/llm/pool``                       平台池快照 (probe=1 逐平台探测 /models)
- ``POST /api/llm/pool/detect``                单平台强制探测 {platform}
- ``GET  /api/llm/pool/routing``               当前三档路由 (task_overrides)
- ``POST /api/llm/pool/route``                 一键写入 yaml 路由 {override_key, provider, model}

密钥存放: POST /api/secrets (provider=<平台名>, 与 SecretsPanel 同一保险箱),
本路由不直接收 key — 避免同值双通道与审计分叉。pi 是 Agent, 在
agent_channels 单列, 不参与模型池。
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.version import APP_VERSION as API_VERSION

router = APIRouter(prefix="/api/llm/pool", tags=["llm-pool"])


@router.get("")
async def get_pool(
    probe: bool = Query(False, description="逐平台探测 /models (出站请求, 每平台 ≤6s)"),
    only: str | None = Query(None, description="仅探测指定平台 name"),
):
    """模型池快照: 内置平台 × 配置状态 × (可选) 可用模型列表。"""
    from backend.services.ai_hub.pool import pool_snapshot

    return {
        "version": API_VERSION,
        **pool_snapshot(probe=probe, only=only),
    }


class DetectRequest(BaseModel):
    platform: str = Field(..., min_length=1, description="平台 name (见 GET /api/llm/pool)")


@router.post("/detect")
async def detect_platform(body: DetectRequest):
    """单平台强制探测 (保存密钥后前端调用)。"""
    from backend.services.ai_hub.pool import PRESETS_BY_NAME, pool_snapshot

    if body.platform not in PRESETS_BY_NAME:
        known = ", ".join(sorted(PRESETS_BY_NAME))
        return {
            "version": API_VERSION, "status": "error",
            "message": f"unknown platform: {body.platform!r} (known: {known})",
        }
    snap = pool_snapshot(probe=True, only=body.platform)
    return {"version": API_VERSION, "status": "ok", **snap}


# ---------------------------------------------------------------------------
# 一键写入 yaml 路由 (DEV-0245) — 池内模型 → task_overrides 三档锚点
# ---------------------------------------------------------------------------
class RouteWriteRequest(BaseModel):
    override_key: str = Field(..., description="t1_score | t3_summary | t3_chunk_summary")
    provider: str = Field(..., min_length=1, description="平台/provider name")
    model: str = Field(..., min_length=1, max_length=120, description="模型名 (探测列表中的 id)")
    force: bool = Field(False, description="跳过写前在线探测 (无 key 仍拒绝)")


@router.get("/routing")
async def get_routing():
    """当前三档路由 (STANDARD/HEAVY/FLASH → provider/model)。"""
    from backend.services.ai_hub.routing_writer import read_routing

    return {"version": API_VERSION, **read_routing()}


@router.post("/route")
async def write_route(body: RouteWriteRequest):
    """一键写入: task_overrides.<override_key> → (provider, model)。

    真实写入前做 key 体检: 无 key 拒绝; 有 key 在线探测, 401/403 拒绝
    (force=true 跳过探测, 无 key 仍拒绝)。provider 不在 llm.yaml 时自动
    从模型池 preset 追加最小 provider 块; 备份 + 原子写; 热重载 ≤5s 生效。
    """
    from backend.services.ai_hub.routing_writer import RoutingWriteError, write_task_override

    try:
        result = write_task_override(
            body.override_key, body.provider, body.model,
            actor="web", force=body.force,
        )
    except RoutingWriteError as e:
        return {"version": API_VERSION, "status": "error", "message": str(e)}
    return {"version": API_VERSION, **result}

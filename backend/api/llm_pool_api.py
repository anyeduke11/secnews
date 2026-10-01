"""LLM 模型池 API — 内置平台目录 + 密钥探测 (DEV-0244)。

- ``GET /api/llm/pool?probe=1[&only=<name>]``  平台池快照 (probe=1 逐平台探测 /models)
- ``POST /api/llm/pool/detect``               单平台强制探测 {platform}

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

"""自动入管配置 API (2026-09-26, design docs/superpowers/specs/2026-09-26-auto-intake-design.md §3.1)。

路由清单:
- ``GET   /api/settings/auto-intake`` — 配置 (kv knowledge.auto_intake.*) + 今日已入管数
- ``PATCH /api/settings/auto-intake`` — 部分更新配置 (校验经 Pydantic ge/le; 写入经
  service → settings_service → audit_log, action=auto_intake.config.set)

R3: 本文件不直连 repository — 读写全部经 auto_intake_service。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.auto_intake_service import (
    get_auto_intake_config,
    set_auto_intake_config,
    today_intaken_count,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class AutoIntakePatchRequest(BaseModel):
    """自动入管配置部分更新 (PATCH 语义: None 字段不动)。

    校验: min_quality_score 0-100 (hotspots.quality_score 同域),
    daily_limit 1-100 (防风暴主闸, 上限封顶防误设 10^9)。
    """

    enabled: bool | None = None
    min_quality_score: int | None = Field(default=None, ge=0, le=100)
    daily_limit: int | None = Field(default=None, ge=1, le=100)
    require_domain_hit: bool | None = None
    actor: str = Field("web")


@router.get("/auto-intake")
async def get_auto_intake() -> dict:
    """读自动入管配置 + 今日已入管数 (source='secnews_auto' 实时 COUNT)。"""
    return {**get_auto_intake_config(), "today_intaken": today_intaken_count()}


@router.patch("/auto-intake")
async def patch_auto_intake(body: AutoIntakePatchRequest) -> dict:
    """更新自动入管配置 (部分更新; 每键写 audit_log 便于消费纠偏溯源)。

    响应带 today_intaken: 前端保存后直接 setState, 契约与 GET 一致。
    """
    updated = set_auto_intake_config(
        enabled=body.enabled,
        min_quality_score=body.min_quality_score,
        daily_limit=body.daily_limit,
        require_domain_hit=body.require_domain_hit,
        actor=body.actor,
    )
    return {**updated, "today_intaken": today_intaken_count()}

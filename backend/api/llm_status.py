"""LLM 状态 API — 暴露当前 provider 状态和降级模式.

Phase 16 — Hybrid AI 状态端点。
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.config.degradation_matrix import create_degradation_matrix
from backend.services.llm_service import llm_service

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/status")
def get_llm_status():
    """返回当前 LLM 配置状态和降级模式."""
    import logging
    logger = logging.getLogger("hotspot.api.llm_status")

    matrix = create_degradation_matrix()
    status = matrix.status()

    # 补充 provider 具体状态
    if llm_service.config and llm_service.config.enabled:
        provider_status = {}
        for name, cfg in llm_service.config.providers.items():
            provider_status[name] = {
                "type": cfg.type,
                "model_score": cfg.models.score,
                "model_summary": cfg.models.summary,
                "configured": True,
            }
        status["providers"] = provider_status
    else:
        status["providers"] = {}

    logger.info("LLM status: %s", status["scenario"])
    return status
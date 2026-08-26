"""LLM 状态 API — 暴露当前 provider 状态和降级模式.

Phase 16 — Hybrid AI 状态端点。
v4.4 — 新增 /evaluate: 大模型评价文章质量 + 提取关键内容（测试/复核）。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.config.degradation_matrix import create_degradation_matrix
from backend.services.ai_hub import llm_service

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


class EvaluateRequest(BaseModel):
    """文章评价测试请求."""
    content: str = Field(..., min_length=10, description="文章正文")
    title: str = ""
    provider: str | None = None   # None → env AI_PROVIDER, 其次 llm.yaml default_provider


@router.post("/evaluate")
async def evaluate_article_endpoint(body: EvaluateRequest):
    """用大模型评价文章质量并提取关键内容（测试用）。

    - provider 未指定时走 ai_hub 解析链：env AI_PROVIDER →
      config/llm.yaml ``default_provider``（不读 settings 表）。
    - 严格模式：LLM 调用失败时返回 ok=False + error（便于测试定位），
      不做静默降级。
    """
    import logging
    logger = logging.getLogger("hotspot.api.llm_status")
    from backend.services.ai_hub import evaluate_article

    try:
        result = await evaluate_article(
            body.content, title=body.title, provider=body.provider,
        )
        return result
    except Exception as e:
        logger.warning("evaluate_article failed: %s", e)
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)[:300]}",
        }
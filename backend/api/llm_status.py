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
    """返回当前 LLM 配置状态和降级模式 + 调用观测面 (v0.6.3 P3-3).

    v0.7 Batch 2 增量: ``effective_provider`` (实际生效的 provider, 经
    env > settings.kv > router > default 四级链解析) 与 ``config_source``
    (解析路径打标: env|settings|router|default)。前端可用这俩字段确认
    "我现在到底用哪个 / 是哪条链生效的"。
    """
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

    # v0.7 Batch 2: 解析路径打标 (与 _resolve_provider 走同一链)
    from backend.services.ai_hub.service import AIService
    status["effective_provider"] = AIService._resolve_provider()
    status["config_source"] = AIService._config_source()

    # v0.7.x Batch ⑥: 密钥来源打标 (env|secrets|none) — 与 AIService._key_source 同链
    ai_svc = AIService()
    status["key_source"] = ai_svc._key_source(status["effective_provider"])

    # v0.6.3 P3-3 观测面: 此前 "AI 是否真在工作" 不可判读
    # (llm_usage_log 只记成功, 失败只进 logger)。诚实口径: 错误环随进程
    # 重启清零, success_rate 是"本进程窗口"而非全天。
    from backend.services.ai_hub.usage import (
        recent_calls,
        recent_llm_errors,
        success_stats_24h,
    )

    status["observability"] = {
        "recent_calls": recent_calls(20),
        "recent_errors": recent_llm_errors(),
        "success_stats": success_stats_24h(),
    }

    logger.info("LLM status: %s", status["scenario"])
    return status


class EvaluateRequest(BaseModel):
    """文章评价测试请求."""
    content: str = Field(..., min_length=10, description="文章正文")
    title: str = ""
    provider: str | None = None   # None → env AI_PROVIDER, 其次 llm.yaml default_provider
    # v0.7.4-image: 场景路由 (deep|light|None)
    # - None → 走老路径 (provider 解析 + _eval_model), 零回归
    # - "deep" → resolve_scenario_model(DEEP) 拿 model (yaml t3_summary = deepseek-v4-pro)
    # - "light" → resolve_scenario_model(LIGHT) 拿 model (yaml t1_score = sensenova-6.8-flash-lite)
    scenario: str | None = Field(None, description="v0.7.4: 场景路由 (deep|light|None)")


@router.post("/evaluate")
async def evaluate_article_endpoint(body: EvaluateRequest):
    """用大模型评价文章质量并提取关键内容（测试用）。

    - provider 未指定时走 ai_hub 解析链：env AI_PROVIDER →
      config/llm.yaml ``default_provider``（不读 settings 表）。
    - scenario 指定时 (v0.7.4): 走 scenarios.resolve_scenario_model 拿 model,
      再以 (provider="sensenova", model=resolved) 注入 ai_hub, 调用结果回写 model 字段
      便于前端看实际生效模型。
    - 严格模式：LLM 调用失败时返回 ok=False + error（便于测试定位），
      不做静默降级。
    """
    import logging
    logger = logging.getLogger("hotspot.api.llm_status")
    from backend.services.ai_hub import evaluate_article

    provider, model = body.provider, None
    if body.scenario:
        try:
            from backend.services.ai_hub.scenarios import (
                Scenario,
                resolve_scenario_model,
            )
            scenario_enum = Scenario(body.scenario)
            route = resolve_scenario_model(scenario_enum)
            # scenario 路由固定 sensenova (yaml task_overrides 一致), 用户可显式覆盖
            provider = provider or "sensenova"
            model = route.model
        except ValueError:
            return {
                "ok": False,
                "error": f"invalid scenario: {body.scenario!r} (must be deep|light|None)",
            }
        except Exception as e:
            logger.warning("scenarios.resolve_scenario_model failed: %s", e)
            # 回落老路径, 不阻断

    try:
        result = await evaluate_article(
            body.content, title=body.title, provider=provider,
        )
        # 透传 model 给前端 (场景路由结果), 便于用户看实际生效模型
        if model and result.get("ok"):
            result["model"] = model
        return result
    except Exception as e:
        logger.warning("evaluate_article failed: %s", e)
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {str(e)[:300]}",
        }
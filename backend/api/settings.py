"""运行时设置 API — 刷新间隔等热配置端点。

- ``POST /api/settings/refresh-interval`` — 更新采集间隔（分钟）
- ``GET  /api/settings/features`` — 扩展 feature flag（前端 useFeatureFlags 数据源）
- ``POST /api/settings/llm-provider`` — 切换运行时默认 LLM provider (v0.7 Batch 2)

v0.7 Batch 2 增量:
- ``llm.default_provider`` 写入 settings.kv (进程内立即生效, 不需重启)
- 每次成功切换写 ``audit_log`` (action=``llm_config.update``)
- 校验: provider 必须在 ``config/llm.yaml`` 已注册 (防 typo 把所有 LLM 调用
  推到一个 yaml 未声明的 provider)
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from backend.config import config
from backend.exceptions import InvalidParamException
from backend.extensions import get_enabled_extensions, is_extension_enabled
from backend.logging_config import logger
from backend.repository.settings_repo import SettingsRepository

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/features")
async def get_features() -> dict:
    """返回全部扩展域的启停状态（feature_gates.toml 派生的运行时视图）。"""
    return {
        "codegarden": is_extension_enabled("codegarden"),
        "codegarden_phase2b": is_extension_enabled("codegarden_phase2b"),
        "mcp": is_extension_enabled("mcp"),
        "sync": is_extension_enabled("sync"),
        "tech_stack": is_extension_enabled("tech_stack"),
        "security_graph": is_extension_enabled("security_graph"),
        "secnews": is_extension_enabled("secnews"),
        "crm": is_extension_enabled("crm"),
        # C4 之后 dsh 才真正可配: 关闭时 /api/dsh/* 返回 404, 界面需如实呈现该状态
        "dsh": is_extension_enabled("dsh"),
        # v0.6.3: workbench_ui 已删除 (workbench 并入 SecNews)
        "enabled_extensions": get_enabled_extensions(),
    }


class RefreshIntervalRequest(BaseModel):
    minutes: int = Field(..., ge=1, le=1440, description="采集间隔（分钟，1-1440）")


@router.post("/refresh-interval")
async def set_refresh_interval(body: RefreshIntervalRequest, request: Request):
    """动态调整 collect_all 采集间隔。

    1. 更新 ``config.collect_interval_seconds``（运行时生效）
    2. 调用 ``scheduler.reschedule()`` 更新 APScheduler 定时器
    """
    interval_seconds = body.minutes * 60

    # 更新 config（运行时生效）
    old = config.collect_interval_seconds
    config.collect_interval_seconds = interval_seconds

    # 更新调度器
    sched = getattr(request.app.state, "scheduler", None)
    if sched is not None:
        try:
            sched.reschedule(interval_seconds)
            logger.info(
                "refresh interval updated: %s min (%ss) -> %s min (%ss)",
                old // 60, old, body.minutes, interval_seconds,
            )
        except Exception as e:
            logger.warning(f"reschedule failed (ignored): {e}")
            return {
                "status": "degraded",
                "message": f"config updated but scheduler reschedule failed: {e}",
                "interval_minutes": body.minutes,
                "interval_seconds": interval_seconds,
            }

    return {
        "status": "ok",
        "message": f"采集间隔已更新为 {body.minutes} 分钟",
        "interval_minutes": body.minutes,
        "interval_seconds": interval_seconds,
    }


# ---------------------------------------------------------------------------
# v0.7 Batch 2 — LLM provider 切换
# ---------------------------------------------------------------------------
class LLMProviderRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64, description="llm.yaml 注册的 provider 名")
    actor: str = Field("web", description="web|system|agent:<name>")


def _list_valid_providers() -> list[str]:
    """读取 ``config/llm.yaml`` 注册的 provider 列表。配置缺失时退回 sensenova/ollama。"""
    try:
        from backend.services.ai_hub.gateway import llm_service
        if llm_service.config and llm_service.config.providers:
            return list(llm_service.config.providers.keys())
    except Exception:
        pass
    return ["sensenova", "ollama"]


@router.post("/llm-provider")
async def set_llm_provider(body: LLMProviderRequest):
    """切换运行时默认 LLM provider (settings.kv 持久化 + audit_log 写入)。

    优先级链: env ``AI_PROVIDER`` > ``llm.default_provider`` (本端点写入) >
    ``config/llm.yaml`` ``default_provider`` (含 router 推荐)。详见
    :meth:`backend.services.ai_hub.service.AIService._resolve_provider`。

    校验: ``provider`` 必须在 ``config/llm.yaml`` 已注册 — 防止 typo 把所有
    LLM 调用推到一个 yaml 未声明的 provider (那时 base_url/api_key_env 都
    取不到, 立即 500)。

    审计: 每次成功切换写一行 ``audit_log`` (action=``llm_config.update``,
    target=``default_provider``, detail={from, to, source})。``record_audit``
    内部全异常吞, 不会因审计失败阻塞业务响应。
    """
    valid = _list_valid_providers()
    if body.provider not in valid:
        raise InvalidParamException(
            f"provider '{body.provider}' not in llm.yaml registry {valid}"
        )

    repo = SettingsRepository()
    old = repo.get("llm.default_provider")
    repo.set("llm.default_provider", body.provider)

    from backend.observability_records import record_audit
    record_audit(
        actor=body.actor,
        action="llm_config.update",
        target="default_provider",
        detail={"from": old, "to": body.provider, "source": "user_switch"},
    )

    logger.info(
        "llm provider switched: {} -> {} (actor={})",
        old, body.provider, body.actor,
    )

    return {
        "status": "ok",
        "old_provider": old,
        "new_provider": body.provider,
        "valid_providers": valid,
    }
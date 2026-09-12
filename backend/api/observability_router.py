"""observability_router.py — v0.7 观测面聚合 router (Batch 2 SQL 下沉后).

聚合 include observability_metrics_api (metrics/breach 查询端点) 并承载
配置 CRUD (thresholds / channels / sampling) + LLM provider 健康度。
不写数据 (写由 TraceIDMiddleware + record_api_call + scheduler job 负责)。
全部无鉴权 (与 /api/health 同级, 观测面板是 ops self-service 工具)。

路由清单:
- (聚合) GET  /api/observability/summary|recent|timeseries|llm-usage
- (聚合) GET  /api/observability/alerts/active · POST .../alerts/{id}/ack
- (聚合) GET  /api/observability/deliveries
- GET/PUT   /api/observability/thresholds
- GET/PUT   /api/observability/channels · POST /api/observability/channels/test
- GET/PUT   /api/observability/sampling
- GET  /api/observability/llm/health · POST /api/observability/llm/health/{provider}/reset

配置类端点无直连 SQL (走 observability_thresholds / alert_dispatcher /
observability_sampling 等 service); 查询类 SQL 已下沉 observability_query_service。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from backend.api.observability_metrics_api import metrics_router

router = APIRouter(prefix="/api/observability", tags=["observability"])

# 聚合 include: metrics/breach 查询端点 (本文件 ≤150 行规格的拆分产物)
router.include_router(metrics_router)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── v0.7 Batch ④: thresholds CRUD ────────────────────────────────────────


@router.get("/thresholds")
def get_thresholds():
    """当前生效阈值规则 — 从 settings.kv 拉, 失败返默认."""
    from backend.services.observability_thresholds import (
        DEFAULT_THRESHOLDS,
        load_thresholds,
    )
    try:
        rules = load_thresholds()
    except Exception:
        rules = DEFAULT_THRESHOLDS
    return {"thresholds": rules, "defaults": DEFAULT_THRESHOLDS, "as_of": _now_iso()}


@router.put("/thresholds")
def put_thresholds(body: dict):
    """覆盖式更新阈值规则 — 校验 → 写 settings.kv → 落 audit_log.

    body 必须是合法 dict 结构 (校验失败 400). 不增量 merge — 全量替换语义清晰.
    """
    from fastapi import HTTPException

    from backend.observability_records import record_audit
    from backend.services.observability_thresholds import (
        DEFAULT_THRESHOLDS,
        save_thresholds,
    )

    if not isinstance(body, dict) or "thresholds" not in body:
        raise HTTPException(status_code=400, detail="body.thresholds must be a dict")
    rules = body["thresholds"]
    try:
        save_thresholds(rules)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    try:
        record_audit(
            action="observability.thresholds.update",
            target="observability.thresholds",
            status="ok",
            detail=f"rules={len(rules)} categories",
        )
    except Exception:
        pass  # 审计失败不影响主流程
    return {"ok": True, "thresholds": rules, "defaults": DEFAULT_THRESHOLDS}


# ── v0.7 Batch ⑧ D2: 告警通道配置 CRUD ───────────────────────────────────


@router.get("/channels")
def get_channels():
    """列出已注册 channel 类型 + 当前配置 (不返回凭据 secret, 仅元数据)."""
    from backend.services.alert_channels import registered_channel_types
    from backend.services.alert_dispatcher import load_channels_config

    return {
        "supported_types": registered_channel_types(),
        "channels": load_channels_config(),
    }


@router.put("/channels")
def put_channels(body: dict):
    """覆盖式更新 channel 配置 — 校验 + 写 settings.kv + audit."""
    from fastapi import HTTPException

    from backend.observability_records import record_audit
    from backend.services.alert_dispatcher import save_channels_config

    if not isinstance(body, dict) or "channels" not in body:
        raise HTTPException(status_code=400, detail="body.channels must be a list")
    chs = body["channels"]
    try:
        save_channels_config(chs)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    try:
        record_audit(
            action="observability.channels.update",
            target="observability.channels",
            status="ok",
            detail=f"channels={len(chs)}",
        )
    except Exception:
        pass
    return {"ok": True, "channels": chs}


@router.post("/channels/test")
async def post_channels_test(body: dict):
    """测试 channel 配置 — 构造一个 mock AlertPayload 试发一次, 不写 alert_deliveries."""
    from fastapi import HTTPException

    from backend.services.alert_channels import (
        AlertPayload,
        build_channel,
        registered_channel_types,
    )

    if not isinstance(body, dict) or "type" not in body:
        raise HTTPException(status_code=400, detail="body.type 必填")
    t = body["type"]
    if t not in registered_channel_types():
        raise HTTPException(
            status_code=400,
            detail=f"未知 channel type: {t}; 支持 {registered_channel_types()}",
        )
    cfg = body.get("config") or {}
    try:
        ch = build_channel(t, **cfg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"build_channel 失败: {e}") from e
    if not ch.is_configured():
        raise HTTPException(status_code=400, detail=f"channel {t} 未配置 (env / config 缺失)")
    payload = AlertPayload(
        metric="test.connection",
        level="warn",
        value=0.0,
        threshold=0.0,
        window_minutes=1,
        detail={"source": "manual_test"},
        fired_at=_now_iso(),
        source="manual_test",
    )
    try:
        res = await ch.send(payload)
        return {"ok": True, "type": t, "result": res}
    except Exception as e:
        return {"ok": False, "type": t, "error": str(e)}


# ── v0.7 Batch ⑧ D4: api_events 采样降级配置 ─────────────────────────────


@router.get("/sampling")
def get_sampling():
    """当前生效的采样配置 (success / error / slow 三档保留率).

    失败/缺失走 DEFAULT_SAMPLING 兜底; 与 thresholds 同款 load 模式.
    """
    from backend.services.observability_sampling import (
        DEFAULT_SAMPLING,
        effective_sampling,
    )

    try:
        cfg = effective_sampling()
    except Exception:
        cfg = None
    return {
        "sampling": (
            {
                "success_rate_pct": cfg.success_rate_pct,
                "error_rate_pct": cfg.error_rate_pct,
                "slow_threshold_ms": cfg.slow_threshold_ms,
                "slow_rate_pct": cfg.slow_rate_pct,
            }
            if cfg is not None
            else DEFAULT_SAMPLING
        ),
        "defaults": DEFAULT_SAMPLING,
        "as_of": _now_iso(),
    }


@router.put("/sampling")
def put_sampling(body: dict):
    """覆盖式更新采样配置 — 校验 → 写 settings.kv → 落 audit_log.

    body.sampling 必填, 含 success_rate_pct / error_rate_pct /
    slow_threshold_ms / slow_rate_pct; 不增量 merge — 全量替换语义清晰.
    校验失败 400; env 覆盖 (HOTSPOT_API_SAMPLING_*) 优先于 settings.kv,
    但这里写 settings.kv 后 env 仍生效 (运维优先).
    """
    from fastapi import HTTPException

    from backend.observability_records import record_audit
    from backend.services.observability_sampling import (
        DEFAULT_SAMPLING,
        SamplingConfig,
        save_sampling,
    )

    if not isinstance(body, dict) or "sampling" not in body:
        raise HTTPException(status_code=400, detail="body.sampling must be a dict")
    raw = body["sampling"]
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="sampling must be a dict")
    try:
        cfg = SamplingConfig.from_dict({**DEFAULT_SAMPLING, **raw})
    except (TypeError, ValueError) as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    save_sampling(cfg)
    try:
        record_audit(
            "web",
            action="observability.sampling.update",
            target="observability.api_sampling",
            detail=(
                f"success={cfg.success_rate_pct}% "
                f"error={cfg.error_rate_pct}% "
                f"slow={cfg.slow_rate_pct}%@{cfg.slow_threshold_ms}ms"
            ),
        )
    except Exception:
        pass
    return {
        "ok": True,
        "sampling": {
            "success_rate_pct": cfg.success_rate_pct,
            "error_rate_pct": cfg.error_rate_pct,
            "slow_threshold_ms": cfg.slow_threshold_ms,
            "slow_rate_pct": cfg.slow_rate_pct,
        },
    }


# ── v0.8.1 Day 4: LLM provider 健康度 (弹性层观测, PLAN §2.1) ────────────
# 并入本 router (core 白名单已有) → routers 73 不变 (PLAN §7 承诺)。

@router.get("/llm/health")
def get_llm_health():
    """per-provider 健康度快照: 窗口 (1m/5m/60m 失败率) + breaker 三态。"""
    try:
        from backend.services.ai_hub.provider_health import get_provider_health
        return {"ok": True, "providers": get_provider_health().snapshot_all()}
    except Exception as e:
        return {"ok": False, "error": str(e), "providers": {}}


@router.post("/llm/health/{provider}/reset")
def reset_llm_breaker(provider: str):
    """手动复位 provider breaker (运维兜底; 迁移写 audit_log)。"""
    try:
        from backend.services.ai_hub.provider_health import get_provider_health
        breaker = get_provider_health().get_breaker(provider)
        pre = breaker.state
        breaker.reset()
        try:
            from backend.observability_records import record_audit
            record_audit(
                actor="web",
                action="llm_breaker.reset",
                target=provider,
                detail={"from": pre, "to": "closed", "reason": "manual"},
            )
        except Exception:
            pass
        return {"ok": True, "provider": provider, "state": breaker.state}
    except Exception as e:
        return {"ok": False, "error": str(e)}


__all__ = ["router"]

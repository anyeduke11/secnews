"""observability_router.py — v0.7 Batch ③ 观测面 query API.

暴露 4 个 GET 端点供前端 Dashboard / StatusBar 用, 不写数据 (写由 TraceIDMiddleware
+ record_api_call + scheduler job 负责). 全部无鉴权 (与 /api/health 同级,
观测面板是 ops self-service 工具, 不属于敏感路径).

约定: 所有 endpoint 同步 (def) — async→def 线程池派发 (P3-1 教训). FastAPI 调
sync def handler 在线程池跑, 不阻塞事件循环.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from backend.repository.db import get_connection

router = APIRouter(prefix="/api/observability", tags=["observability"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/summary")
def get_summary():
    """最近 1h 概览: total / error_count / error_rate / p95_latency_ms.

    直接从 api_events 单表聚合, 不读 hourly roll-up (后者有 5min 延迟且
    仅供趋势查询). Dashboard 卡片用此 endpoint.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn = get_connection()
    cur = conn.execute(
        "SELECT COUNT(*) AS total, "
        "       SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END) AS errors "
        "FROM api_events WHERE occurred_at > ?",
        (since,),
    )
    row = cur.fetchone()
    total = int(row["total"] or 0)
    errors = int(row["errors"] or 0)
    error_rate = (errors / total * 100) if total else 0.0

    # p95 走子查询 OFFSET (与 aggregator 同款近似)
    cur = conn.execute(
        "SELECT duration_ms FROM api_events "
        "WHERE occurred_at > ? "
        "ORDER BY duration_ms LIMIT 1 "
        "OFFSET (SELECT CAST(COUNT(*) * 0.95 AS INTEGER) FROM api_events "
        "         WHERE occurred_at > ?)",
        (since, since),
    )
    p95_row = cur.fetchone()
    p95 = int(p95_row["duration_ms"]) if p95_row else 0

    # Top 5 慢路径
    cur = conn.execute(
        "SELECT path_template, COUNT(*) AS n, MAX(duration_ms) AS mx "
        "FROM api_events WHERE occurred_at > ? "
        "GROUP BY path_template ORDER BY mx DESC LIMIT 5",
        (since,),
    )
    top_slow = [
        {"path_template": r["path_template"], "count": int(r["n"]),
         "max_ms": int(r["mx"])}
        for r in cur.fetchall()
    ]

    return {
        "window_minutes": 60,
        "total": total,
        "errors": errors,
        "error_rate_pct": round(error_rate, 2),
        "p95_latency_ms": p95,
        "top_slow_paths": top_slow,
        "as_of": _now_iso(),
    }


@router.get("/recent")
def get_recent(limit: int = Query(20, ge=1, le=200)):
    """api_events 最近 N 条 — StatusBar 与 Dashboard 实时面板用.

    按 occurred_at DESC 返回, 默认 20 条 (StatusBar 5s 刷新, 200 上限避免
    一次拉太多).
    """
    conn = get_connection()
    cur = conn.execute(
        "SELECT id, trace_id, method, path_template, status, "
        "       duration_ms, error, occurred_at "
        "FROM api_events ORDER BY occurred_at DESC LIMIT ?",
        (int(limit),),
    )
    return {
        "items": [
            {
                "id": int(r["id"]),
                "trace_id": r["trace_id"],
                "method": r["method"],
                "path_template": r["path_template"],
                "status": int(r["status"]),
                "duration_ms": int(r["duration_ms"]),
                "error": r["error"],
                "occurred_at": r["occurred_at"],
            }
            for r in cur.fetchall()
        ],
        "as_of": _now_iso(),
    }


@router.get("/timeseries")
def get_timeseries(hours: int = Query(24, ge=1, le=168),
                   path_template: str | None = None):
    """时序数据 (前端画图用) — 从 api_metrics_hourly 读聚合预计算.

    默认 24h, 上限 7d (168h). 按 hour 升序返回.
    """
    conn = get_connection()
    if path_template:
        cur = conn.execute(
            "SELECT hour, total, errors, p50_ms, p95_ms, max_ms "
            "FROM api_metrics_hourly "
            "WHERE hour > ? AND path_template = ? "
            "ORDER BY hour ASC",
            (
                (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
                    "%Y-%m-%dT%H"
                ),
                path_template,
            ),
        )
    else:
        cur = conn.execute(
            "SELECT hour, path_template, total, errors, p50_ms, p95_ms, max_ms "
            "FROM api_metrics_hourly "
            "WHERE hour > ? "
            "ORDER BY hour ASC",
            (
                (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
                    "%Y-%m-%dT%H"
                ),
            ),
        )
    return {
        "hours": hours,
        "path_template": path_template,
        "points": [
            {
                "hour": r["hour"],
                "path_template": r["path_template"] if "path_template" in r.keys() else path_template,
                "total": int(r["total"]),
                "errors": int(r["errors"]),
                "p50_ms": int(r["p50_ms"]),
                "p95_ms": int(r["p95_ms"]),
                "max_ms": int(r["max_ms"]),
            }
            for r in cur.fetchall()
        ],
        "as_of": _now_iso(),
    }


@router.get("/llm-usage")
def get_llm_usage_recent(limit: int = Query(20, ge=1, le=200)):
    """llm_usage_log 最近 N 条 — 与 Batch ③ /api/llm/status observability 块
    复用, 但这个 endpoint 返回原始行而非聚合统计.

    与 /api/llm/status 区别: 后者返回 24h success_rate 等聚合, 本 endpoint
    返回原始调用行. 供 Dashboard "实时" 卡片用.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT id, provider, model, task, ok, latency_ms, "
            "       error, scene, started_at "
            "FROM llm_usage_log ORDER BY started_at DESC LIMIT ?",
            (int(limit),),
        )
    except Exception:
        return {"items": [], "as_of": _now_iso()}
    return {
        "items": [
            {
                "id": int(r["id"]),
                "provider": r["provider"],
                "model": r["model"],
                "task": r["task"],
                "ok": bool(r["ok"]),
                "latency_ms": int(r["latency_ms"]) if r["latency_ms"] is not None else None,
                "error": r["error"],
                "scene": r["scene"],
                "started_at": r["started_at"],
            }
            for r in cur.fetchall()
        ],
        "as_of": _now_iso(),
    }


# ── v0.7 Batch ④: alerts + thresholds CRUD ───────────────────────────────


@router.get("/alerts/active")
def get_alerts_active():
    """活跃告警 (acked=0, fired_at 在最近 24h), 按 critical 先 / 触发时间倒序.

    前端 Dashboard 顶部活跃横幅 + StatusBar 角标共用. 限制 24h 窗口避免
    历史告警堆积; acked 告警走 /alerts/recent (Batch ⑤ 视情况再加).
    """
    conn = get_connection()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        cur = conn.execute(
            "SELECT id, level, metric, value, threshold, window_minutes, "
            "       detail, fired_at, cooldown_until "
            "FROM observability_alerts "
            "WHERE acked = 0 AND fired_at > ? "
            "ORDER BY "
            "  CASE level WHEN 'critical' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END, "
            "  fired_at DESC",
            (cutoff,),
        )
        items = []
        for r in cur.fetchall():
            items.append({
                "id": int(r["id"]),
                "level": r["level"],
                "metric": r["metric"],
                "value": float(r["value"]),
                "threshold": float(r["threshold"]),
                "window_minutes": int(r["window_minutes"]),
                "detail": r["detail"],
                "fired_at": r["fired_at"],
                "cooldown_until": r["cooldown_until"],
            })
        return {
            "items": items,
            "critical_count": sum(1 for i in items if i["level"] == "critical"),
            "warn_count": sum(1 for i in items if i["level"] == "warn"),
            "as_of": _now_iso(),
        }
    except Exception as e:
        # 失败降级返空 — 不阻塞前端展示, 仅日志
        from backend.logging_config import logger
        logger.warning(f"get_alerts_active failed: {e}")
        return {"items": [], "critical_count": 0, "warn_count": 0, "as_of": _now_iso()}


@router.post("/alerts/{alert_id}/ack")
def post_alerts_ack(alert_id: int):
    """标记告警已读 (acked=1). 不删 — 保留追溯链路.

    不写 audit_log (acm 是 self-service 操作, 非策略变更).
    """
    conn = get_connection()
    now = _now_iso()
    cur = conn.execute(
        "UPDATE observability_alerts SET acked = 1, acked_at = ? "
        "WHERE id = ? AND acked = 0",
        (now, int(alert_id)),
    )
    if cur.rowcount == 0:
        # 已 ack 或 id 不存在 — idempotent 返 200, 客户端无需刷新
        return {"ok": True, "id": int(alert_id), "already": True}
    return {"ok": True, "id": int(alert_id), "acked_at": now}


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


# ── v0.7 Batch ⑧ D2: 告警通道配置 CRUD ───────────────────────────────


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


@router.get("/deliveries")
def get_deliveries(limit: int = Query(50, ge=1, le=500)):
    """列最近 alert_deliveries (审计 "告警是否真的发出去了")."""
    from backend.repository.db import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT id, alert_id, channel, ok, status_code, error, delivered_at "
        "FROM alert_deliveries ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {
        "deliveries": [
            {
                "id": r["id"],
                "alert_id": r["alert_id"],
                "channel": r["channel"],
                "ok": bool(r["ok"]),
                "status_code": r["status_code"],
                "error": r["error"],
                "delivered_at": r["delivered_at"],
            }
            for r in rows
        ]
    }


# ── v0.7 Batch ⑧ D4: api_events 采样降级配置 ───────────────────────────


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
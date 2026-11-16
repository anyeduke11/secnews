"""observability_alerts 发射服务 — 写表 + SSE 广播 + 渠道投递 (单一实现)。

本模块是 v0.7 Batch ④ 告警基建的**唯一写入口**: 原先逻辑内嵌在
``backend/scheduler/jobs/maintenance.py::_fire_alert``, v0.8.9 P5 需要从
services 层 (执行体 runner, 同步上下文) 发射越界告警 → 下沉到 services 层,
scheduler 侧改为委托, 避免两份实现漂移。

三条通道 (与 v0.7 语义一致):
1. ``observability_alerts`` 表 — 持久化 + cooldown (同 metric+level 防刷屏)
2. SSE ``observability.breach`` — 前端横幅 / StatusBar 角标
3. ``alert_dispatcher`` — 外部渠道 (webhook / email / slack …) 投递

失败语义: 告警自身失败 **只 log 不抛** — 告警链路故障不得拖垮被观察的主链
(与 v0.7 Batch ④ 契约一致)。注意: 越界事实本身仍由 run.error / agent_runs
显式承载, 告警是附加可见性, 不是唯一真相来源。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.logging_config import logger

_log = logger.bind(component="observability_alert")

DEFAULT_WINDOW_MINUTES = 10080  # 7d (v0.7 默认)
DEFAULT_COOLDOWN_MINUTES = 1440  # 1d (v0.7 默认)


async def fire_alert(
    *,
    metric: str,
    level: str,
    value: float = 0.0,
    detail: dict[str, Any] | None = None,
    source: str = "observability",
    threshold: float = 0.0,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    dedupe_key: str | None = None,
) -> int | None:
    """发射一条告警 → 返回 observability_alerts 行 id (被 cooldown 抑制则 None)。

    ``dedupe_key``: 去重维度 (默认 None = 保持 v0.7 语义: 同 (metric, level)
    在 cooldown 窗口内只发一条)。给定时, 抑制判定额外要求 **同 dedupe_key**
    —— 即「同一事件源内的重复合并, 不同事件源各自可见」。

    为何需要: 执行体越界若沿用全局 cooldown, 一个窗口内多个不同 run 的
    真实越界会被吞掉 (演练④ 实测: 6 次越界只落 1 条告警) —— 违反「失败必
    可见」。执行体传 ``dedupe_key=run_id``, 既防同一 run 重复刷屏, 又不吞
    跨 run 的真实越界。

    任何内部失败只 log — 告警链路不抛 (主链不被告警拖垮)。
    """
    alert_id: int | None = None
    now = datetime.now(timezone.utc)
    try:
        from backend.repository.db import get_connection

        conn = get_connection()
        existing = conn.execute(
            "SELECT id, detail, cooldown_until FROM observability_alerts "
            "WHERE metric = ? AND level = ? AND acked = 0 "
            "ORDER BY fired_at DESC LIMIT 1",
            (metric, level),
        ).fetchone()
        suppressed = bool(
            existing and existing["cooldown_until"] > now.isoformat()
        )
        if suppressed and dedupe_key is not None:
            # 同 (metric, level) 但**不同** dedupe_key → 不抑制 (各自可见)。
            try:
                prev = json.loads(existing["detail"] or "{}")
            except (TypeError, ValueError):
                prev = {}
            suppressed = prev.get("_dedupe_key") == dedupe_key
        if not suppressed:
            payload = dict(detail or {})
            if dedupe_key is not None:
                payload["_dedupe_key"] = dedupe_key
            conn.execute(
                "INSERT INTO observability_alerts "
                "(level, metric, value, threshold, window_minutes, detail, "
                "fired_at, cooldown_until, acked) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    level, metric, value, threshold,
                    window_minutes, json.dumps(payload, ensure_ascii=False),
                    now.isoformat(),
                    (now + timedelta(minutes=cooldown_minutes)).isoformat(),
                ),
            )
            alert_id = conn.execute(
                "SELECT last_insert_rowid() AS id"
            ).fetchone()["id"]
    except Exception as e:
        _log.error(f"{metric} alert write failed: {e}")

    if alert_id is None:
        return None

    try:
        from backend.core.events import publish_event

        await publish_event("observability.breach", {
            "alert_id": alert_id,
            "level": level,
            "metric": metric,
            "value": value,
            "threshold": threshold,
        })
    except Exception as e:
        _log.debug(f"publish_event {metric} failed: {e}")

    try:
        from backend.services.alert_channels import AlertPayload
        from backend.services.alert_dispatcher import dispatch

        await dispatch(
            AlertPayload(
                metric=metric,
                level=level,
                value=value,
                threshold=threshold,
                window_minutes=window_minutes,
                detail=detail or {},
                fired_at=now.isoformat(),
                source=source,
            ),
            alert_id=alert_id,
        )
    except Exception as e:
        _log.debug(f"dispatch {metric} failed: {e}")

    return alert_id


def fire_alert_sync(
    *,
    metric: str,
    level: str,
    value: float = 0.0,
    detail: dict[str, Any] | None = None,
    source: str = "observability",
    threshold: float = 0.0,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    dedupe_key: str | None = None,
) -> int | None:
    """同步上下文的发射入口 (执行体 runner 在工作线程里调用)。

    已在事件循环中 → 建 task (不阻塞调用方); 无事件循环 → ``asyncio.run``。
    与 ``backend/services/alert_service.py`` 的同步→异步桥接同款。
    """
    kwargs = dict(
        metric=metric,
        level=level,
        value=value,
        detail=detail,
        source=source,
        threshold=threshold,
        window_minutes=window_minutes,
        cooldown_minutes=cooldown_minutes,
        dedupe_key=dedupe_key,
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        loop.create_task(fire_alert(**kwargs))
        return None
    return asyncio.run(fire_alert(**kwargs))


__all__ = ["fire_alert", "fire_alert_sync"]

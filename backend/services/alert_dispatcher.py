"""v0.7 Batch ⑧ D2: 告警分发器 — 拉 channels 配置 → 选实例 → 并发投递 → 留痕。

设计
----
- **配置源**: settings.kv ``observability.channels`` 数组 [{type, config: {...}}, ...]
  缺省 = 仅 ``status_bar`` (内置前端, 不需要外部 webhook)
- **delivery 表**: ``alert_deliveries`` (新增), 字段: alert_id, channel, ok, status_code,
  error, delivered_at — 用于后台审计 "告警是否真的发出去了"
- **失败隔离**: 每条 channel try/except, 一条失败不影响其他; 全部 swallow + log
- **不阻塞主路径**: 用 ``asyncio.gather(return_exceptions=True)`` 并发投递
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from backend.logging_config import logger
from backend.repository.db import get_connection
from backend.repository.settings_repo import SettingsRepository
from backend.services.alert_channels import (
    AlertPayload,
    build_channel,
    registered_channel_types,
)

SETTINGS_KEY_CHANNELS = "observability.channels"

# 默认 channel 配置 (内置 status_bar 不需要外部 channel)
DEFAULT_CHANNELS_CONFIG: list[dict[str, Any]] = []


def load_channels_config(repo: SettingsRepository | None = None) -> list[dict[str, Any]]:
    """从 settings.kv 读 channel 配置; 缺失走默认空列表."""
    repo = repo or SettingsRepository()
    raw = repo.get(SETTINGS_KEY_CHANNELS, None)
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)]
    return DEFAULT_CHANNELS_CONFIG


def save_channels_config(channels: list[dict[str, Any]],
                         repo: SettingsRepository | None = None) -> None:
    """校验 schema 后写 settings.kv."""
    _validate_channels(channels)
    repo = repo or SettingsRepository()
    repo.set(SETTINGS_KEY_CHANNELS, channels)


def _validate_channels(channels: list[dict[str, Any]]) -> None:
    """校验 [{type, config}, ...] 结构."""
    if not isinstance(channels, list):
        raise ValueError("channels 必须是 list")
    valid_types = set(registered_channel_types())
    for i, ch in enumerate(channels):
        if not isinstance(ch, dict):
            raise ValueError(f"channels[{i}] 必须是 dict")
        t = ch.get("type")
        if t not in valid_types:
            raise ValueError(
                f"channels[{i}].type={t} 不支持; 合法: {sorted(valid_types)}"
            )
        cfg = ch.get("config")
        if cfg is not None and not isinstance(cfg, dict):
            raise ValueError(f"channels[{i}].config 必须是 dict 或缺省")


def _build_channels() -> list:
    """根据 settings 配置建 channel 实例列表 (跳过未配置的)."""
    cfg = load_channels_config()
    channels = []
    for c in cfg:
        t = c["type"]
        params = c.get("config") or {}
        try:
            ch = build_channel(t, **params)
            if ch.is_configured():
                channels.append(ch)
            else:
                logger.debug(f"channel {t} 未配置, 跳过")
        except Exception as e:
            logger.warning(f"build_channel {t} 失败: {e}")
    return channels


def _record_delivery(alert_id: int | None, channel_type: str,
                     ok: bool, detail: dict[str, Any]) -> None:
    """写 alert_deliveries 表留痕 (吞异常, 不阻塞 dispatch)."""
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO alert_deliveries "
            "(alert_id, channel, ok, status_code, error, delivered_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                alert_id,
                channel_type,
                1 if ok else 0,
                detail.get("status_code"),
                (detail.get("error") or "")[:500] if detail.get("error") else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    except Exception as e:
        logger.debug(f"record_delivery failed: {e}")


async def dispatch(payload: AlertPayload, *,
                   alert_id: int | None = None) -> dict[str, Any]:
    """投递一条告警到所有已配置 channel.

    Returns: {channel_type: {ok: bool, ...detail}}
    不抛异常 (单个 channel 失败 swallow + log).
    """
    channels = _build_channels()
    if not channels:
        return {"dispatched": 0, "channels": {}}

    async def _one(ch) -> tuple[str, dict[str, Any]]:
        try:
            res = await ch.send(payload)
            return ch.channel_type, {"ok": True, **res}
        except Exception as e:
            logger.warning(f"channel {ch.channel_type} send failed: {e}")
            return ch.channel_type, {"ok": False, "error": str(e)}

    results = await asyncio.gather(*[_one(c) for c in channels])

    summary: dict[str, Any] = {}
    for ch_type, detail in results:
        summary[ch_type] = detail
        _record_delivery(
            alert_id=alert_id,
            channel_type=ch_type,
            ok=detail.get("ok", False),
            detail=detail,
        )
    return {"dispatched": len(channels), "channels": summary}


__all__ = [
    "dispatch",
    "load_channels_config",
    "registered_channel_types",
    "save_channels_config",
]
"""v0.7 Batch ⑧ D4: api_events 采样降级配置.

存储: settings.kv key = "observability.api_sampling", JSON-encoded dict.
失败/缺失走 ``DEFAULT_SAMPLING`` 兜底 (保守默认: 成功 10%, 错误/慢请求 100%).

执行: TraceIDMiddleware 在 record_api_call 前调 ``should_record_api_event()``;
error/slow 永远保留 (保 error_rate 与 p95 精度), 仅成功路径按 ``success_rate_pct``
随机降级。失败 swallow 走原路径, 不影响响应.
"""
from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass
from typing import Any

from backend.repository.settings_repo import SettingsRepository

log = logging.getLogger("hotspot.observability.sampling")

DEFAULT_SAMPLING: dict[str, Any] = {
    # 成功请求保留率: 1-100 整数百分比. 0 = 全降级 (极端); 100 = 全保留.
    "success_rate_pct": 10,
    # 错误请求 (status >= 500) 保留率: 默认 100% 保 error_rate 精度.
    "error_rate_pct": 100,
    # 慢请求阈值 (ms): duration_ms >= 该值视为慢请求, 默认 100% 保留保 p95 长尾.
    "slow_threshold_ms": 2000,
    "slow_rate_pct": 100,
    # 测试 / 调试可临时 env 覆盖 (e.g. HOTSPOT_API_SAMPLING_SUCCESS=100)
}

SETTINGS_KEY = "observability.api_sampling"


@dataclass(frozen=True)
class SamplingConfig:
    success_rate_pct: int
    error_rate_pct: int
    slow_threshold_ms: int
    slow_rate_pct: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SamplingConfig:
        return cls(
            success_rate_pct=_clamp_pct(int(d.get("success_rate_pct", DEFAULT_SAMPLING["success_rate_pct"]))),
            error_rate_pct=_clamp_pct(int(d.get("error_rate_pct", DEFAULT_SAMPLING["error_rate_pct"]))),
            slow_threshold_ms=max(0, int(d.get("slow_threshold_ms", DEFAULT_SAMPLING["slow_threshold_ms"]))),
            slow_rate_pct=_clamp_pct(int(d.get("slow_rate_pct", DEFAULT_SAMPLING["slow_rate_pct"]))),
        )


def _clamp_pct(v: int) -> int:
    return max(0, min(100, v))


def load_sampling(repo: SettingsRepository | None = None) -> SamplingConfig:
    """从 settings.kv 拉采样配置; 缺失/坏值走 DEFAULT_SAMPLING 兜底."""
    repo = repo or SettingsRepository()
    raw = repo.get(SETTINGS_KEY, None)
    if not isinstance(raw, dict):
        raw = dict(DEFAULT_SAMPLING)
    return SamplingConfig.from_dict({**DEFAULT_SAMPLING, **raw})


def save_sampling(cfg: SamplingConfig, repo: SettingsRepository | None = None) -> None:
    """写 settings.kv; 同时校验 schema."""
    d = {
        "success_rate_pct": cfg.success_rate_pct,
        "error_rate_pct": cfg.error_rate_pct,
        "slow_threshold_ms": cfg.slow_threshold_ms,
        "slow_rate_pct": cfg.slow_rate_pct,
    }
    repo = repo or SettingsRepository()
    repo.set(SETTINGS_KEY, d)


def effective_sampling() -> SamplingConfig:
    """env override + settings.kv 合并; 测试与运维优先.

    env: HOTSPOT_API_SAMPLING_{SUCCESS|ERROR|SLOW}_{RATE_PCT|THRESHOLD_MS}=...
    仅 int 注入; 没设就走 settings.kv/DEFAULT 兜底.
    """
    cfg = load_sampling()

    def _env_int(name: str) -> int | None:
        v = os.environ.get(name)
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            log.warning("env %s=%r not int, ignored", name, v)
            return None

    s = _env_int("HOTSPOT_API_SAMPLING_SUCCESS_RATE_PCT")
    e = _env_int("HOTSPOT_API_SAMPLING_ERROR_RATE_PCT")
    sl = _env_int("HOTSPOT_API_SAMPLING_SLOW_RATE_PCT")
    sm = _env_int("HOTSPOT_API_SAMPLING_SLOW_THRESHOLD_MS")
    if s is None and e is None and sl is None and sm is None:
        return cfg
    return SamplingConfig(
        success_rate_pct=s if s is not None else cfg.success_rate_pct,
        error_rate_pct=e if e is not None else cfg.error_rate_pct,
        slow_rate_pct=sl if sl is not None else cfg.slow_rate_pct,
        slow_threshold_ms=sm if sm is not None else cfg.slow_threshold_ms,
    )


def should_record_api_event(*, status: int, duration_ms: float) -> bool:
    """判定本次请求是否写入 api_events.

    规则 (按顺序评估):
    1. status >= 500 → error_rate_pct
    2. duration_ms >= slow_threshold_ms → slow_rate_pct
    3. 其他 (成功 / 4xx) → success_rate_pct

    测试环境常将 success_rate_pct 设 100, 此时全采; rate=0 时全不采.
    任何 ValueError / TypeError 都返回 True (fail-open, 观测不能丢).
    """
    try:
        cfg = effective_sampling()
        if int(status) >= 500:
            return _hit(cfg.error_rate_pct)
        if float(duration_ms) >= cfg.slow_threshold_ms:
            return _hit(cfg.slow_rate_pct)
        return _hit(cfg.success_rate_pct)
    except Exception as e:
        log.debug("should_record_api_event fail-open: %s", e)
        return True


def _hit(rate_pct: int) -> bool:
    if rate_pct >= 100:
        return True
    if rate_pct <= 0:
        return False
    return random.random() * 100 < rate_pct


__all__ = [
    "DEFAULT_SAMPLING",
    "SETTINGS_KEY",
    "SamplingConfig",
    "effective_sampling",
    "load_sampling",
    "save_sampling",
    "should_record_api_event",
]
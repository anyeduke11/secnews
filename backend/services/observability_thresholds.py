"""v0.7 Batch ④: 观测阈值规则引擎.

存储: settings.kv key = "observability.thresholds", JSON-encoded dict.
失败/缺失走 ``DEFAULT_THRESHOLDS`` 兜底 (Batch ④ plan §4.1, 保守默认).

执行: ``scheduler_threshold_check_job`` 每小时跑一次, 拉 settings 规则,
扫最近 window_minutes 数据, 评估 breach → 写 observability_alerts.
cooldown 防止同一阈值风暴刷屏; acked 标志前端"已读"。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.repository.settings_repo import SettingsRepository

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "api": {
        "error_rate_pct": {"warn": 5, "critical": 15, "window_minutes": 60},
        "p95_latency_ms": {"warn": 800, "critical": 2000, "window_minutes": 60},
    },
    "llm": {
        "error_rate_pct": {"warn": 10, "critical": 30, "window_minutes": 60},
    },
    "job": {
        "failure_rate_pct": {"warn": 10, "critical": 25, "window_minutes": 60},
    },
    "audit": {
        "llm_config_change_per_hour": {"warn": 10, "critical": 50, "window_minutes": 60},
    },
    "alerts": {
        "channels": ["status_bar"],
        "cooldown_minutes": 15,
    },
}

SETTINGS_KEY = "observability.thresholds"


@dataclass(frozen=True)
class Breach:
    """一次阈值越界评估结果."""
    level: str           # "warn" | "critical"
    metric: str          # "api.error_rate_pct" 等
    value: float
    threshold: float
    window_minutes: int
    detail: dict[str, Any] | None = None  # path_template / job_type 等上下文


def load_thresholds(repo: SettingsRepository | None = None) -> dict[str, Any]:
    """从 settings.kv 拉阈值规则; 缺失/坏值走 DEFAULT_THRESHOLDS 兜底."""
    repo = repo or SettingsRepository()
    raw = repo.get(SETTINGS_KEY, None)
    if not isinstance(raw, dict):
        return DEFAULT_THRESHOLDS
    return raw


def save_thresholds(rules: dict[str, Any], repo: SettingsRepository | None = None) -> None:
    """校验 schema 后写 settings.kv (dict 天然 JSON 编码)."""
    _validate(rules)
    repo = repo or SettingsRepository()
    repo.set(SETTINGS_KEY, rules)


def _validate(rules: dict[str, Any]) -> None:
    """schema 校验: 4 大类规则结构 + 数值非负 + warn < critical."""
    if not isinstance(rules, dict):
        raise ValueError("thresholds must be a dict")
    for category in ("api", "llm", "job", "audit"):
        cat_rules = rules.get(category)
        if cat_rules is None:
            continue
        if not isinstance(cat_rules, dict):
            raise ValueError(f"thresholds.{category} must be a dict")
        for metric, spec in cat_rules.items():
            if not isinstance(spec, dict):
                raise ValueError(f"thresholds.{category}.{metric} must be a dict")
            for level in ("warn", "critical"):
                v = spec.get(level)
                if v is None:
                    continue
                if not isinstance(v, (int, float)) or v < 0:
                    raise ValueError(
                        f"thresholds.{category}.{metric}.{level} must be a non-negative number"
                    )
            warn = spec.get("warn")
            critical = spec.get("critical")
            if warn is not None and critical is not None and warn >= critical:
                raise ValueError(
                    f"thresholds.{category}.{metric}: warn ({warn}) must be < critical ({critical})"
                )
            w = spec.get("window_minutes")
            if w is not None and (not isinstance(w, int) or w <= 0 or w > 24 * 60):
                raise ValueError(f"thresholds.{category}.{metric}.window_minutes out of range")


def evaluate_api(
    *,
    error_rate_pct: float,
    p95_latency_ms: float,
    thresholds: dict[str, Any],
) -> list[Breach]:
    """对 api 指标评估, 返回所有越界 (warn + critical 各 ≤1)."""
    breaches: list[Breach] = []
    api_t = thresholds.get("api", {})
    for metric_name, value in (
        ("error_rate_pct", error_rate_pct),
        ("p95_latency_ms", p95_latency_ms),
    ):
        spec = api_t.get(metric_name)
        if not spec:
            continue
        for level in ("warn", "critical"):
            threshold = spec.get(level)
            if threshold is None:
                continue
            if value >= threshold:
                breaches.append(Breach(
                    level=level,
                    metric=f"api.{metric_name}",
                    value=float(value),
                    threshold=float(threshold),
                    window_minutes=int(spec.get("window_minutes", 60)),
                ))
    return breaches


def evaluate(
    *,
    api_summary: dict[str, Any],
    thresholds: dict[str, Any],
) -> list[Breach]:
    """从 /api/observability/summary 形态 (含 total/errors/error_rate_pct/p95_latency_ms)
    评估越界 — 当前仅 api; llm/job/audit 由各 job 自行扩展."""
    return evaluate_api(
        error_rate_pct=float(api_summary.get("error_rate_pct", 0)),
        p95_latency_ms=float(api_summary.get("p95_latency_ms", 0)),
        thresholds=thresholds,
    )


def cooldown_until(now: datetime | None = None, minutes: int = 15) -> str:
    """下一次允许同 metric 触发的最早时间 (ISO UTC)."""
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(minutes=minutes)).isoformat()
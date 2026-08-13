"""成本监控 — LLM 调用费用记录与限额告警.

Phase 16 — Hybrid AI 成本控制。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Literal, Optional

from backend.config.llm_schema import CostAlert, LLMConfig
from backend.repository.db import get_connection

logger = logging.getLogger("hotspot.cost_monitor")

# 成本估算 (USD per 1M tokens)
COST_PER_1M_TOKENS: Dict[str, float] = {
    "gpt-4o-mini": 0.15,
    "gpt-4o": 5.0,
    "qwen-turbo": 0.3,
    "qwen-plus": 0.8,
    "claude-3-5-haiku-20241022": 0.8,
    "claude-3-5-sonnet-20241022": 3.0,
}


def _estimate_cost(model: str, tokens: int) -> float:
    """估算一次 LLM 调用的 USD 成本."""
    if tokens <= 0:
        return 0.0
    rate = COST_PER_1M_TOKENS.get(model, 0.5)
    return (tokens / 1_000_000) * rate


class CostMonitor:
    """LLM 调用成本监控.

    Usage::

        from backend.services.cost_monitor import cost_monitor

        cost_monitor.record_usage("openai", "gpt-4o-mini", "score", 150, 0.0001, 250)
        if not cost_monitor.check_limits():
            # 超限额，触发告警
    """

    def __init__(self, llm_config: Optional[LLMConfig] = None):
        self._config = llm_config

    @property
    def config(self) -> Optional[CostAlert]:
        if self._config and self._config.enabled:
            return self._config.cost_alert
        return None

    def record_usage(
        self,
        provider: str,
        model: str,
        task: str,
        tokens: int,
        cost_usd: float,
        latency_ms: int,
    ) -> None:
        """记录一次 LLM 调用用量."""
        try:
            conn = get_connection()
            conn.execute(
                "INSERT INTO llm_usage_log "
                "(provider, model, task, tokens, cost_usd, latency_ms, occurred_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    provider,
                    model,
                    task,
                    tokens,
                    cost_usd,
                    latency_ms,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        except Exception as e:
            logger.warning("Failed to record LLM usage: %s", e)

    def check_limits(self) -> bool:
        """检查日/月 USD 限额.

        Returns
        -------
        bool
            True 表示未超限额，可以继续调用；
            False 表示超限额，需要触发告警。
        """
        alert_cfg = self.config
        if alert_cfg is None:
            return True

        try:
            conn = get_connection()
            now = datetime.now(timezone.utc)

            # 日限额检查
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total "
                "FROM llm_usage_log WHERE occurred_at >= ?",
                (today_start.isoformat(),),
            ).fetchone()
            daily_total = row["total"] if row else 0.0

            if daily_total >= alert_cfg.daily_usd_limit:
                logger.warning(
                    "Daily cost limit exceeded: $%.4f >= $%.2f",
                    daily_total,
                    alert_cfg.daily_usd_limit,
                )
                self._trigger_alert("daily", daily_total, alert_cfg.daily_usd_limit)
                return False

            # 月限额检查
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total "
                "FROM llm_usage_log WHERE occurred_at >= ?",
                (month_start.isoformat(),),
            ).fetchone()
            monthly_total = row["total"] if row else 0.0

            if monthly_total >= alert_cfg.monthly_usd_limit:
                logger.warning(
                    "Monthly cost limit exceeded: $%.4f >= $%.2f",
                    monthly_total,
                    alert_cfg.monthly_usd_limit,
                )
                self._trigger_alert("monthly", monthly_total, alert_cfg.monthly_usd_limit)
                return False

        except Exception as e:
            logger.warning("Failed to check cost limits: %s", e)

        return True

    def get_daily_cost(self) -> float:
        """获取当日总成本 (USD)."""
        try:
            conn = get_connection()
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total "
                "FROM llm_usage_log WHERE occurred_at >= ?",
                (today_start.isoformat(),),
            ).fetchone()
            return row["total"] if row else 0.0
        except Exception:
            return 0.0

    def get_monthly_cost(self) -> float:
        """获取当月总成本 (USD)."""
        try:
            conn = get_connection()
            now = datetime.now(timezone.utc)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total "
                "FROM llm_usage_log WHERE occurred_at >= ?",
                (month_start.isoformat(),),
            ).fetchone()
            return row["total"] if row else 0.0
        except Exception:
            return 0.0

    def get_on_exceeded_strategy(self) -> str:
        """获取超限额时的处理策略."""
        alert_cfg = self.config
        if alert_cfg is None:
            return "warn"
        return alert_cfg.on_exceeded

    @staticmethod
    def _trigger_alert(period: str, current: float, limit: float) -> None:
        """触发成本告警，写入 cg_events 表."""
        try:
            conn = get_connection()
            conn.execute(
                "INSERT INTO cg_events "
                "(title, description, event_type, severity, status, source, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"LLM cost limit exceeded ({period})",
                    f"Current: ${current:.4f}, Limit: ${limit:.2f}",
                    "cost_alert",
                    "warning",
                    "pending",
                    "cost_monitor",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            logger.info("Cost alert event created: %s limit exceeded", period)
        except Exception as e:
            logger.warning("Failed to create cost alert event: %s", e)


# 全局单例（初始无配置，由 LLMService 初始化后更新）
cost_monitor = CostMonitor()


__all__ = [
    "CostMonitor",
    "cost_monitor",
    "_estimate_cost",
]
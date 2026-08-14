"""统一代理池，支持 failover + health score.

Phase 16 — Crawl4ai 集成配套。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

from backend.repository.db import get_connection

logger = logging.getLogger("hotspot.proxy_pool")

DEFAULT_PROXY_CONFIG_PATH = Path(__file__).resolve().parent.parent / "proxy_config.json"


class ProxyPool:
    """统一代理池，支持 failover + health score."""

    def __init__(self, config_path: Path | None = None):
        cfg_path = config_path or DEFAULT_PROXY_CONFIG_PATH
        self._load_config(cfg_path)
        self._health_score: dict[str, float] = {}
        self._init_health()

    def _load_config(self, path: Path) -> None:
        if not path.exists():
            self.primary = ""
            self.backups: list[str] = []
            self.strategy = "failover"
            return
        with open(path) as f:
            cfg = json.load(f)
        self.primary = cfg.get("http_proxy", "")
        self.backups = cfg.get("backup_proxies", [])
        self.strategy = cfg.get("rotation_strategy", "failover")

    def _init_health(self) -> None:
        self._health_score[self.primary] = 1.0
        for p in self.backups:
            self._health_score[p] = 0.5

    def get_next(self) -> str:
        """按策略选下一个代理."""
        candidates = [self.primary, *self.backups]
        if self.strategy == "failover":
            for proxy in candidates:
                if self._health_score.get(proxy, 0) > 0.3:
                    return proxy
            return self.primary  # 全失败仍试主
        # round_robin: 按 health_score 加权选（简化：直接返回第一个可用的）
        for proxy in candidates:
            if self._health_score.get(proxy, 0) > 0.3:
                return proxy
        return self.primary

    def mark_failed(self, proxy: str) -> None:
        """失败：health_score -= 0.3（最低 0）."""
        current = self._health_score.get(proxy, 0.5)
        self._health_score[proxy] = max(0.0, current - 0.3)
        self._log_event(proxy, "failed")
        logger.warning("Proxy failed: %s (score=%.1f)", proxy, self._health_score[proxy])

    def mark_success(self, proxy: str) -> None:
        """成功：health_score 恢复 +0.1（最高 1.0）."""
        current = self._health_score.get(proxy, 0.5)
        self._health_score[proxy] = min(1.0, current + 0.1)
        self._log_event(proxy, "success")

    def _log_event(self, proxy: str, event: str) -> None:
        try:
            conn = get_connection()
            conn.execute(
                "INSERT INTO proxy_health_log "
                "(proxy_url, event, health_score, occurred_at) "
                "VALUES (?, ?, ?, ?)",
                (proxy, event, self._health_score.get(proxy, 0.5),
                 datetime.now(timezone.utc).isoformat()),
            )
        except Exception:
            pass  # 日志表不存在时静默失败

    async def startup_health_check(self) -> None:
        """服务启动时测试每个代理是否可达."""
        test_url = "https://www.google.com/generate_204"
        if not self.primary:
            logger.info("No proxy configured, skipping health check")
            return
        for proxy in [self.primary, *self.backups]:
            if not proxy:
                continue
            try:
                async with httpx.AsyncClient(proxies=proxy, timeout=5) as client:
                    await client.get(test_url)
                    self.mark_success(proxy)
                    logger.info("Proxy OK: %s (score=%.1f)", proxy, self._health_score[proxy])
            except Exception as e:
                self.mark_failed(proxy)
                logger.warning("Proxy DEAD: %s (%s)", proxy, e)


# 全局单例
proxy_pool = ProxyPool()


__all__ = ["ProxyPool", "proxy_pool"]
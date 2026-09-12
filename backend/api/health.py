"""Phase 4+5 /api/health router — 增强版 (/api/stats 见 health_stats.py)。

Phase 5 扩展字段：
- /api/health: uptime_s, db.size_mb, db.wal, db.integrity, cache.hit_rate

Batch 2 SQL 下沉: 全部 DB 探测 (wal/integrity/row count/collection_runs)
迁至 backend.services.health_query_service; 本文件仅保留 HTTP 语义
(payload 组装 + 无 DB 的 scheduler/proxy 探测)。
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from backend.cache import hit_rate
from backend.cache import stats as cache_stats
from backend.config import config
from backend.observability import set_start_time, uptime_s
from backend.services.health_query_service import (
    collectors_last_run,
    db_health,
)

router = APIRouter(prefix="/api", tags=["health"])

# 服务启动时间（模块级，process lifetime）
_START_TIME = time.time()
# 同时写入 observability 模块，让其它模块统一读取
set_start_time(_START_TIME)

# 项目版本 (单一来源 backend/version.py)
from backend.version import APP_VERSION as VERSION


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scheduler_health(sched=None) -> dict:
    """Phase 8: 接受可选的 sched 参数（来自 app.state），回退去模块 singleton。"""
    try:
        if sched is None:
            from backend.scheduler.scheduler import get_scheduler

            sched = get_scheduler()
        if sched is None or sched.scheduler is None:
            return {"ok": False, "reason": "not started", "jobs": []}
        jobs_list = [
            {"id": j.id, "name": j.name, "next": str(j.next_run_time)}
            for j in sched.scheduler.get_jobs()
        ]
        return {
            "ok": True,
            "jobs": [j["id"] for j in jobs_list],
            "details": jobs_list,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _proxy_health() -> dict:
    """代理组件: 模式 + 生效代理 + 熔断器状态 (cadence 修正批 T5 附加字段)。"""
    try:
        from backend.proxy_config import (
            configured_proxy_url,
            load_proxy_settings,
            proxy_health_snapshot,
        )

        settings = load_proxy_settings()
        snap = proxy_health_snapshot()
        effective = configured_proxy_url("https://example.com/", settings) or ""
        return {
            "ok": True,
            "mode": settings.mode,
            "enabled": settings.mode != "off" and bool(effective),
            "effective_proxy": effective,
            "circuit_open": snap["circuit_open"],
            "open_remaining_seconds": snap["open_remaining_seconds"],
            "consecutive_failures": snap["consecutive_failures"],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _build_health_payload(sched) -> dict:
    """同步构建 health payload（在 thread pool 中执行）。"""
    components = {
        "db": db_health(),
        "scheduler": _scheduler_health(sched=sched),
        "cache": {"ok": True, **cache_stats(), "hit_rate": hit_rate()},
        "collectors": collectors_last_run(),
        "proxy": _proxy_health(),
    }
    overall_ok = all(c.get("ok", False) for c in components.values())
    status = ("down" if not components["db"]["ok"] else "degraded") if not overall_ok else "ok"
    return {
        "version": VERSION,
        "status": status,
        "uptime_s": round(uptime_s(), 2),
        "uptime_seconds": round(uptime_s(), 2),  # 兼容旧字段
        "collect_interval_seconds": config.collect_interval_seconds,
        "components": components,
        "time": _now_iso(),
    }


@router.get("/health")
async def health(request: Request):
    """健康检查（Phase 5 增强版 + Phase 8: app.state 读取 scheduler）。

    Phase 9 修复：整体 payload 构建放 thread pool，避免 collect 期间阻塞 event loop。
    """
    sched = getattr(request.app.state, "scheduler", None)
    return await asyncio.to_thread(_build_health_payload, sched)

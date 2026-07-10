"""Phase 4+5 /api/health router — 增强版 + 内部 /api/stats。

Phase 5 扩展字段：
- /api/health: uptime_s, db.size_mb, db.wal, db.integrity, cache.hit_rate
- /api/stats:  collect_runs_24h, success_rate_24h, avg_collect_duration_ms,
              last_fallback_at
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request

from backend.cache import hit_rate, stats as cache_stats
from backend.config import config
from backend.domain.enums import Category
from backend.logging_config import logger
from backend.observability import set_start_time, uptime_s
from backend.repository.db import get_connection

router = APIRouter(prefix="/api", tags=["health"])

# 服务启动时间（模块级，process lifetime）
_START_TIME = time.time()
# 同时写入 observability 模块，让其它模块统一读取
set_start_time(_START_TIME)

# 项目版本
VERSION = "1.2.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_size_mb() -> float:
    """返回 DB 文件大小（MB）。WAL 文件不计入。"""
    try:
        path = config.db_path
        if os.path.exists(path):
            return round(os.path.getsize(path) / 1024 / 1024, 2)
    except Exception as e:
        logger.warning(f"_db_size_mb failed: {e}")
    return 0.0


def _db_wal() -> dict[str, Any]:
    """检查 WAL 模式是否启用。"""
    try:
        conn = get_connection()
        row = conn.execute("PRAGMA journal_mode").fetchone()
        mode = row[0] if row else "unknown"
        return {
            "enabled": mode.lower() == "wal",
            "mode": mode.lower(),
        }
    except Exception as e:
        return {"enabled": False, "error": str(e)[:200]}


_INTEGRITY_CACHE: dict[str, Any] = {}
_INTEGRITY_CACHE_TTL_S = 60.0


def _db_integrity() -> dict[str, Any]:
    """运行 PRAGMA integrity_check（Phase 8: 60s TTL 缓存）。

    PRAGMA integrity_check 扫描整个 DB，20MB → 500ms+。健康检查每次
    都跑会成为热路径瓶颈。60s TTL 让 /api/health 稳定在 <50ms，同时
    仍然保证每分钟有一次完整校验。
    """
    now = time.time()
    cached = _INTEGRITY_CACHE.get("result")
    if cached and (now - cached["ts"]) < _INTEGRITY_CACHE_TTL_S:
        return {k: v for k, v in cached["data"].items()}
    try:
        conn = get_connection()
        row = conn.execute("PRAGMA integrity_check").fetchone()
        result = row[0] if row else "unknown"
        data = {"ok": result == "ok", "result": result}
        _INTEGRITY_CACHE["result"] = {"ts": now, "data": data}
        return data
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _hotspots_row_count() -> int:
    """返回 hotspots 表的当前行数。

    Phase 8 Task 5.4: 这个值会被 _db_health 用来检测"truncate"型损坏。
    PRAGMA integrity_check 不会因为表为空而报错，所以需要额外的
    row count 检查让 chaos 演练的"truncate hotspots" 能被检测出来。
    """
    try:
        conn = get_connection()
        row = conn.execute("SELECT COUNT(*) AS n FROM hotspots").fetchone()
        return int(row["n"]) if row and row["n"] is not None else 0
    except Exception as e:
        logger.warning(f"_hotspots_row_count failed: {e}")
        return -1


def _db_health() -> dict[str, Any]:
    """检查 DB 可达 + 测延迟 + row count 完整性。

    Phase 8 Task 5.4: 额外检查 hotspots 表的 row count。
    - 若 hotspots 为空（count == 0），视为损坏（chaos 4 演练场景）。
    - 返回 ``hotspots_count`` 字段供调用方判断。
    """
    start = time.time()
    try:
        conn = get_connection()
        conn.execute("SELECT 1").fetchone()
        latency_ms = round((time.time() - start) * 1000, 2)
        hotspots_count = _hotspots_row_count()
        # Phase 8 修复: 空的 hotspots 表视为损坏（chaos 4 演练场景检测）
        # 任何正常运行的实例至少会有 seed / 抓取产生的行。
        ok = hotspots_count > 0
        data: dict[str, Any] = {
            "ok": ok,
            "latency_ms": latency_ms,
            "size_mb": _db_size_mb(),
            "wal": _db_wal(),
            "integrity": _db_integrity(),
            "hotspots_count": hotspots_count,
        }
        if not ok:
            data["error"] = f"hotspots table is empty (count={hotspots_count})"
        return data
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _scheduler_health(sched=None) -> dict[str, Any]:
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


def _collectors_health() -> dict[str, Any]:
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT started_at, item_count FROM collection_runs "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return {"ok": True, "last_run": None, "items_last": 0}
        return {
            "ok": True,
            "last_run": row["started_at"],
            "items_last": row["item_count"],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _proxy_health() -> dict[str, Any]:
    try:
        from backend.proxy_config import load_proxy_settings

        settings = load_proxy_settings()
        return {"ok": True, "mode": settings.mode}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _build_health_payload(sched) -> dict:
    """同步构建 health payload（在 thread pool 中执行）。"""
    components = {
        "db": _db_health(),
        "scheduler": _scheduler_health(sched=sched),
        "cache": {"ok": True, **cache_stats(), "hit_rate": hit_rate()},
        "collectors": _collectors_health(),
        "proxy": _proxy_health(),
    }
    overall_ok = all(c.get("ok", False) for c in components.values())
    if not overall_ok:
        status = "down" if not components["db"]["ok"] else "degraded"
    else:
        status = "ok"
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


def _build_stats_payload() -> dict:
    """同步构建 stats payload（在 thread pool 中执行）。"""
    try:
        conn = get_connection()
        row = conn.execute("SELECT COUNT(*) AS n FROM hotspots").fetchone()
        total_hotspots = int(row["n"] or 0) if row else 0
    except Exception as e:
        logger.warning(f"stats: hotspot count failed: {e}")
        total_hotspots = 0

    # 24h 采集统计
    collect_runs_24h = 0
    success_rate_24h = 0.0
    avg_collect_duration_ms = 0
    last_fallback_at = None

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        row = conn.execute(
            "SELECT COUNT(*) AS n, "
            "SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS ok, "
            "AVG(duration_ms) AS avg_dur, "
            "MAX(fallback_count) AS max_fallback "
            "FROM collection_runs WHERE started_at >= ?",
            (cutoff,),
        ).fetchone()
        if row and row["n"]:
            collect_runs_24h = int(row["n"])
            success_rate_24h = round(
                (int(row["ok"] or 0) / collect_runs_24h), 4
            )
            avg_collect_duration_ms = int(row["avg_dur"] or 0)
    except Exception as e:
        logger.warning(f"stats: 24h collect stats failed: {e}")

    try:
        # 找最近一次任何 fallback_count > 0 的 run
        row = conn.execute(
            "SELECT started_at FROM collection_runs "
            "WHERE fallback_count > 0 "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if row:
            last_fallback_at = row["started_at"]
    except Exception as e:
        logger.warning(f"stats: last fallback lookup failed: {e}")

    # Phase 6: 数据一致性校验
    try:
        from backend.cache import list_cache
        from backend.repository.hotspot_repo import HotspotRepository

        hrepo = HotspotRepository()
        db_counts = hrepo.count_by_category_db()

        # Try to get cached list counts
        cached_counts: dict[str, int] = {}
        for cat in Category:
            try:
                cached = list_cache.get(f"hotspots:list:{cat.value}:7d")
                if cached and isinstance(cached, dict):
                    cc = cached.get("category_counts", {})
                    if cc.get(cat.value):
                        cached_counts[cat.value] = cc[cat.value]
            except Exception:
                pass

        # If no cached counts (cold start), fall back to all 0
        if not cached_counts:
            for cat in Category:
                cached_counts[cat.value] = 0

        drift = []
        for cat in Category:
            c_val = cat.value
            cached = cached_counts.get(c_val, 0)
            db_count = db_counts.get(c_val, 0)
            # Drift: list shows more than DB has, or vice versa
            # (we compare: list counts should never exceed DB all-time counts)
            if cached > 0 and db_count == 0:
                drift.append({"category": c_val, "cached": cached, "db": db_count, "note": "no_data"})
            elif cached > db_count:
                drift.append({"category": c_val, "cached": cached, "db": db_count})

        consistency_check = {
            "status": "ok" if not drift else "drift",
            "drift": drift,
        }
    except Exception as e:
        logger.warning(f"stats: consistency check failed: {e}")
        consistency_check = {"status": "unknown", "drift": [], "error": str(e)[:200]}

    return {
        "version": VERSION,
        "cache": {
            "stats": cache_stats(),
            "hit_rate": hit_rate(),
        },
        "db": {
            "hotspots_total": total_hotspots,
            "size_mb": _db_size_mb(),
            "wal": _db_wal(),
        },
        "uptime_s": round(uptime_s(), 2),
        "collect_runs_24h": collect_runs_24h,
        "success_rate_24h": success_rate_24h,
        "avg_collect_duration_ms": avg_collect_duration_ms,
        "last_fallback_at": last_fallback_at,
        "consistency_check": consistency_check,
        "time": _now_iso(),
    }


@router.get("/stats")
async def stats():
    """内部统计（Phase 5 扩展）。

    Phase 9 修复：整体 payload 构建放 thread pool，避免 collect 期间阻塞 event loop。
    """
    return await asyncio.to_thread(_build_stats_payload)

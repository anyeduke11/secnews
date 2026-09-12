"""health_query_service — /api/health 与 /api/stats 的 DB 探测查询服务.

Batch 2 SQL 下沉: backend/api/health.py 内 6 处直连 SQL (WAL/integrity/
row count/SELECT 1 延迟/collection_runs 末次/stats 三查询) 收敛到本服务。
纯文件大小/代理/调度器探测仍在路由层 (无 DB)。

- integrity_check 有 60s TTL 缓存 (Phase 8: PRAGMA 全表扫描 500ms+,
  不能进健康检查热路径), 缓存随本模块迁移。
- consistency_check (Phase 6 数据漂移校验) 同步迁入: 读 HotspotRepository
  + list_cache, 属服务编排逻辑而非 HTTP 语义。

依赖方向: 仅 import backend.repository.db / backend.repository.hotspot_repo /
backend.cache / backend.config, 不触碰 backend.api。
"""
from __future__ import annotations

import os
import time
from typing import Any

from backend.config import config
from backend.logging_config import logger
from backend.repository.db import get_connection


def db_size_mb() -> float:
    """返回 DB 文件大小（MB）。WAL 文件不计入。"""
    try:
        path = config.db_path
        if os.path.exists(path):
            return round(os.path.getsize(path) / 1024 / 1024, 2)
    except Exception as e:
        logger.warning(f"db_size_mb failed: {e}")
    return 0.0


def db_wal() -> dict[str, Any]:
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


def db_integrity() -> dict[str, Any]:
    """运行 PRAGMA integrity_check（Phase 8: 60s TTL 缓存）。

    PRAGMA integrity_check 扫描整个 DB，20MB → 500ms+。健康检查每次
    都跑会成为热路径瓶颈。60s TTL 让 /api/health 稳定在 <50ms，同时
    仍然保证每分钟有一次完整校验。
    """
    now = time.time()
    cached = _INTEGRITY_CACHE.get("result")
    if cached and (now - cached["ts"]) < _INTEGRITY_CACHE_TTL_S:
        return dict(cached["data"].items())
    try:
        conn = get_connection()
        row = conn.execute("PRAGMA integrity_check").fetchone()
        result = row[0] if row else "unknown"
        data = {"ok": result == "ok", "result": result}
        _INTEGRITY_CACHE["result"] = {"ts": now, "data": data}
        return data
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def hotspots_row_count() -> int:
    """返回 hotspots 表的当前行数。

    Phase 8 Task 5.4: 这个值会被 db_health 用来检测"truncate"型损坏。
    PRAGMA integrity_check 不会因为表为空而报错，所以需要额外的
    row count 检查让 chaos 演练的"truncate hotspots" 能被检测出来。
    """
    try:
        conn = get_connection()
        row = conn.execute("SELECT COUNT(*) AS n FROM hotspots").fetchone()
        return int(row["n"]) if row and row["n"] is not None else 0
    except Exception as e:
        logger.warning(f"hotspots_row_count failed: {e}")
        return -1


def db_health() -> dict[str, Any]:
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
        count = hotspots_row_count()
        # Phase 8 修复: 空的 hotspots 表视为损坏（chaos 4 演练场景检测）
        # 任何正常运行的实例至少会有 seed / 抓取产生的行。
        ok = count > 0
        data: dict[str, Any] = {
            "ok": ok,
            "latency_ms": latency_ms,
            "size_mb": db_size_mb(),
            "wal": db_wal(),
            "integrity": db_integrity(),
            "hotspots_count": count,
        }
        if not ok:
            data["error"] = f"hotspots table is empty (count={count})"
        return data
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def collectors_last_run() -> dict[str, Any]:
    """最近一次采集 run (started_at, item_count) + watchdog 恢复时间戳。

    v1.0 R21 服务恢复: collection_runs 在 warm.db (M2-T6 分库后),
    主 conn 走 ATTACH 跨库查询。
    """
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT started_at, item_count FROM warm.collection_runs "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        # Phase 8: 暴露 watchdog 最近恢复时间戳
        try:
            from backend.services.catchup_service import get_last_orphan_recovery_at

            last_orphan_recovery_at = get_last_orphan_recovery_at()
        except Exception:
            last_orphan_recovery_at = None
        if row is None:
            return {
                "ok": True,
                "last_run": None,
                "items_last": 0,
                "last_orphan_recovery_at": last_orphan_recovery_at,
            }
        return {
            "ok": True,
            "last_run": row["started_at"],
            "items_last": row["item_count"],
            "last_orphan_recovery_at": last_orphan_recovery_at,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def stats_hotspots_total() -> int:
    """/api/stats: hotspots 总行数。失败时返回 0 (与原路由行为一致)。"""
    try:
        row = get_connection().execute(
            "SELECT COUNT(*) AS n FROM hotspots"
        ).fetchone()
        return int(row["n"] or 0) if row else 0
    except Exception as e:
        logger.warning(f"stats: hotspot count failed: {e}")
        return 0


def collect_stats_24h() -> dict[str, Any]:
    """/api/stats: 24h 采集统计 (runs/success_rate/avg_duration)。"""
    from datetime import datetime, timedelta, timezone

    collect_runs_24h = 0
    success_rate_24h = 0.0
    avg_collect_duration_ms = 0
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        row = get_connection().execute(
            "SELECT COUNT(*) AS n, "
            "SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS ok, "
            "AVG(duration_ms) AS avg_dur, "
            "MAX(fallback_count) AS max_fallback "
            "FROM warm.collection_runs WHERE started_at >= ?",
            (cutoff,),
        ).fetchone()
        if row and row["n"]:
            collect_runs_24h = int(row["n"])
            success_rate_24h = round((int(row["ok"] or 0) / collect_runs_24h), 4)
            avg_collect_duration_ms = int(row["avg_dur"] or 0)
    except Exception as e:
        logger.warning(f"stats: 24h collect stats failed: {e}")
    return {
        "collect_runs_24h": collect_runs_24h,
        "success_rate_24h": success_rate_24h,
        "avg_collect_duration_ms": avg_collect_duration_ms,
    }


def last_fallback_at() -> str | None:
    """/api/stats: 最近一次 fallback_count > 0 的 run 时间。"""
    try:
        row = get_connection().execute(
            "SELECT started_at FROM warm.collection_runs "
            "WHERE fallback_count > 0 "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if row:
            return row["started_at"]
    except Exception as e:
        logger.warning(f"stats: last fallback lookup failed: {e}")
    return None


def consistency_check() -> dict[str, Any]:
    """Phase 6: 数据一致性校验 (list cache 分类计数 vs DB 全量计数)。"""
    try:
        from backend.cache import list_cache
        from backend.domain.enums import Category
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

        return {
            "status": "ok" if not drift else "drift",
            "drift": drift,
        }
    except Exception as e:
        logger.warning(f"stats: consistency check failed: {e}")
        return {"status": "unknown", "drift": [], "error": str(e)[:200]}

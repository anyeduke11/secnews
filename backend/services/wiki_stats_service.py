"""Wiki 统计服务 — DB 投影优先的管线/知识库统计 (v0.6.3 卡顿根治 P0-1)。

历史问题 (2026-08-30 深审 H1 根因): ``/api/kl/pipeline/stats`` 与
``/api/secnews/pipeline`` / ``/api/secnews/knowledge`` 每次请求都在
**事件循环线程上同步扫描全量 4149 个 wiki md 文件** (funnel + liveness
各一遍 = 8298 次 read_text + YAML 解析, 零缓存), 被 30s 轮询与 SSE
重拉反复触发 → 事件循环周期性冻结数秒 → 全站请求假死。

本模块的修复分层:
1. **funnel / stage 分布 / 条目计数 → DB 投影** (``warm.knowledge_items.lifecycle``
   与 HOT ``knowledge_concepts``) — 这才是管线真实口径 (T1-T5 触发器读写
   的就是 DB; md frontmatter 是归档副本, 数字本就不同: 实测 md kl:raw=48
   vs DB kl:raw=2)。单条 GROUP BY 查询, 微秒级。
2. **liveness (书签存活三态) → md 扫描 + 30s TTL 缓存** — ``alive`` 字段
   尚无 DB 投影, 保留 md 真源口径但摊薄成本 (30s 内所有调用共享一次扫描),
   且必须经 ``asyncio.to_thread`` 调用, 不再阻塞事件循环。
"""
from __future__ import annotations

import threading
import time
from typing import Any

from backend.kl_pipeline.obs.funnel import _LEGACY_TO_STAGE, UNKNOWN_STAGE
from backend.kl_pipeline.queue import STAGES
from backend.logging_config import logger
from backend.repository.db import get_connection

_LIFECYCLE_SQL = (
    "SELECT COALESCE(lifecycle, '') AS lifecycle, COUNT(*) AS c "
    "FROM warm.knowledge_items GROUP BY lifecycle"
)

# liveness md 扫描的 TTL 缓存 (秒): 30s 内所有调用共享一次全量扫描
_LIVENESS_TTL_S = 30.0
_liveness_cache: dict[str, tuple[float, dict]] = {}
_liveness_lock = threading.Lock()


# ---------------------------------------------------------------------------
# funnel / stage 分布 — DB 投影 (warm.knowledge_items.lifecycle)
# ---------------------------------------------------------------------------
def funnel_from_db(conn: Any = None) -> list[dict[str, Any]]:
    """管线漏斗 — 从 DB 投影统计, 与 md 归档口径的差异见模块 docstring。

    Args:
        conn: 可注入连接 (测试/调用方持有 thread-local 连接时传 self.db);
            缺省用 get_connection()。

    Returns:
        ``[{"stage": "kl:raw", "count": n}, ..., {"stage": "unknown", "count": m}]``
        (stage 顺序与 STAGES 一致, 值域外/历史值经 _LEGACY_TO_STAGE 归一,
        归不进去的进 unknown, 与 funnel_stats 语义对齐)
    """
    counts: dict[str, int] = dict.fromkeys(STAGES, 0)
    counts[UNKNOWN_STAGE] = 0
    try:
        rows = (conn or get_connection()).execute(_LIFECYCLE_SQL).fetchall()
    except Exception as e:
        logger.warning(f"funnel_from_db query failed: {e}")
        return [{"stage": s, "count": c} for s, c in counts.items()]

    for row in rows:
        stage = (row["lifecycle"] or "").strip()
        if not stage:
            continue
        stage = _LEGACY_TO_STAGE.get(stage, stage)
        if stage in counts:
            counts[stage] += row["c"]
        else:
            counts[UNKNOWN_STAGE] += row["c"]
    return [{"stage": s, "count": c} for s, c in counts.items()]


def stage_distribution_from_db(conn: Any = None) -> dict[str, int]:
    """知识库 tab 的 lifecycle 分布 (同 funnel 数据源, dict 形态)。"""
    dist: dict[str, int] = {}
    try:
        rows = (conn or get_connection()).execute(_LIFECYCLE_SQL).fetchall()
    except Exception as e:
        logger.warning(f"stage_distribution_from_db query failed: {e}")
        return dist
    for row in rows:
        stage = (row["lifecycle"] or "").strip() or "unknown"
        dist[stage] = dist.get(stage, 0) + row["c"]
    return dist


def knowledge_stats_from_db(conn: Any = None) -> dict[str, Any]:
    """知识库统计 (条目数/概念数/生命周期分布) — 全部走 DB, 零文件 IO。"""
    items = 0
    concepts = 0
    conn = conn or get_connection()
    try:
        items = conn.execute(
            "SELECT COUNT(*) FROM warm.knowledge_items"
        ).fetchone()[0]
        concepts = conn.execute(
            "SELECT COUNT(*) FROM knowledge_concepts"
        ).fetchone()[0]
    except Exception as e:
        logger.warning(f"knowledge_stats_from_db query failed: {e}")
    return {
        "items": items,
        "concepts": concepts,
        "stage_distribution": stage_distribution_from_db(conn),
    }


# ---------------------------------------------------------------------------
# liveness — md 扫描 + 30s TTL 缓存 (alive 字段尚无 DB 投影)
# ---------------------------------------------------------------------------
def liveness_from_md_cached(wiki_fs: Any, *, ttl_s: float = _LIVENESS_TTL_S) -> dict:
    """书签存活三态 (total/alive/dead/unknown), 30s TTL 进程内缓存。

    必须在 worker 线程调用 (端点侧 ``asyncio.to_thread``); 缓存过期后
    第一个调用者做一次全量扫描, 其余调用者拿缓存。
    """
    if wiki_fs is None:
        return {"total": 0, "alive": 0, "dead": 0, "unknown": 0}

    key = str(getattr(wiki_fs, "root", None) or id(wiki_fs))
    now = time.monotonic()
    with _liveness_lock:
        hit = _liveness_cache.get(key)
        if hit and now - hit[0] < ttl_s:
            return hit[1]

    # 锁外扫描 (耗时 IO), 双重检查避免并发重复扫
    from backend.wiki_fs.liveness import liveness_counts

    result = liveness_counts(wiki_fs)
    with _liveness_lock:
        _liveness_cache[key] = (time.monotonic(), result)
    return result


def invalidate_stats_cache() -> None:
    """wiki 写入方 (kl管线/导入) 可调用: 清掉 liveness 缓存让下一请求重扫。"""
    with _liveness_lock:
        _liveness_cache.clear()


__all__ = [
    "funnel_from_db",
    "invalidate_stats_cache",
    "knowledge_stats_from_db",
    "liveness_from_md_cached",
    "stage_distribution_from_db",
]

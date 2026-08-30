"""v0.7 — 源清单普查 (Source Census): 全站信源数量的单一口径。

为什么需要这个模块
------------------
历史上"有多少个源、多少个死了"同时有三套互不相容的答案:

- ``GET /api/sources/health``      → 枚举 ``source_stats`` **历史行** (152 行, 含
  已无 collector 抓取的孤儿与跨 category 重名)
- ``GET /api/sources/health/v2``   → 枚举 ``crawler_sources`` 调度表 (含 disabled)
- ``GET /api/sources/health/trend``→ 枚举 ``hotspots.source`` 去重名 (47 个)

三个数字各自"没错", 但混在同一个"健康度"名义下就互相打脸。本模块不改变任何
判定算法, 只做两件事:

1. **统一分母**: 以 ``crawler_sources WHERE enabled=1`` 为"当前真实注册的源"权威
   口径 (采集器 ``collectors/base.py:_load_sources_from_registry`` 就是读这张表),
   并把 ``source_stats`` 里不再被任何 collector 抓取的行标成 orphan 而不是静默计入。
2. **统一词汇**: 给出三套状态之间的显式等价表, 让 119 dead / 44 unknown / 42 red
   这类数字可以被比较, 而不是被当成三个互相矛盾的结论。

注意: Phase 9 (liveness) 与 Phase 4 (throughput trend) 度量的是不同事实, 按
``source_health_service`` 的设计说明**并存且互不替代** —— 收敛的是口径, 不是把它们
合并成一个数。
"""
from __future__ import annotations

from typing import Any

from backend.repository.db import get_connection

# 三套状态词汇的等价关系 (用于跨端点比较, 不改变任何一侧的判定算法)。
# key = 语义档位, value = 各体系里落在该档位的取值名。
STATUS_EQUIVALENCE: dict[str, dict[str, str]] = {
    "ok":       {"phase9_liveness": "active", "phase3_scheduler": "healthy",  "phase4_trend": "green"},
    "watch":    {"phase9_liveness": "stale",  "phase3_scheduler": "degraded", "phase4_trend": "yellow"},
    "failing":  {"phase9_liveness": "dead",   "phase3_scheduler": "unhealthy","phase4_trend": "red"},
    "no_signal": {"phase9_liveness": "-",     "phase3_scheduler": "unknown",  "phase4_trend": "-"},
}


def registry_snapshot() -> dict[str, Any]:
    """读 ``crawler_sources`` 注册表 (采集器实际抓取的权威清单)。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT category, name, enabled FROM crawler_sources"
    ).fetchall()
    enabled = {(str(r["category"]), str(r["name"])) for r in rows if int(r["enabled"] or 0) == 1}
    disabled = {(str(r["category"]), str(r["name"])) for r in rows if int(r["enabled"] or 0) != 1}
    return {
        "registered_total": len(rows),
        "enabled_total": len(enabled),
        "disabled_total": len(disabled),
        "enabled_keys": enabled,
        "keys": {(str(r["category"]), str(r["name"])) for r in rows},
    }


def stats_snapshot() -> list[dict[str, Any]]:
    """读 ``source_stats`` 历史累计行 (Phase 9 liveness 的数据面)。"""
    conn = get_connection()
    return [dict(r) for r in conn.execute(
        "SELECT category, source_name, status, total_items, last_seen_at FROM source_stats"
    ).fetchall()]


def build_census(reg: dict[str, Any] | None = None) -> dict[str, Any]:
    """把注册表与历史统计对齐, 返回全站统一的源数量口径。

    Parameters
    ----------
    reg:
        可选的 ``registry_snapshot()`` 结果; 同一请求里已读过注册表时传入,
        避免重复查询。不传则本函数自行读取。

    Returns
    -------
    dict
        - ``registered_enabled`` / ``registered_disabled`` / ``registry_total``:
          采集器当前真实注册情况 (分母以此为准)
        - ``stats_rows``: ``source_stats`` 历史行数 (旧分母)
        - ``orphan_rows``: 有历史行但**已不在注册表** (没有任何 collector 会再抓它)
        - ``untracked_count``: 在注册表里启用但还没有任何统计行的源数 (新接入源)
        - ``status_equivalence``: 三套状态词汇的等价表
    """
    reg = reg or registry_snapshot()
    stats = stats_snapshot()

    orphans = [
        {
            "category": str(r["category"]),
            "source_name": str(r["source_name"]),
            "status": str(r["status"] or ""),
            "total_items": int(r["total_items"] or 0),
        }
        for r in stats
        if (str(r["category"]), str(r["source_name"])) not in reg["keys"]
    ]
    stats_keys = {(str(r["category"]), str(r["source_name"])) for r in stats}
    untracked = sorted(reg["enabled_keys"] - stats_keys)

    # 注册表启用且已有统计行的, 才是"可判定的活跃清单"
    live_keys = reg["enabled_keys"]
    counted = [r for r in stats if (str(r["category"]), str(r["source_name"])) in live_keys]

    def _n(status: str) -> int:
        return sum(1 for r in counted if str(r["status"] or "") == status)

    return {
        "registry_total": reg["registered_total"],
        "registered_enabled": reg["enabled_total"],
        "registered_disabled": reg["disabled_total"],
        "stats_rows": len(stats),
        "orphan_rows": len(orphans),
        "orphan_sample": orphans[:10],
        "untracked_count": len(untracked),
        # 只统计"注册且启用"的源 —— 这是前端心跳条应当使用的分母
        "counted_total": len(counted),
        "counted_active": _n("active"),
        "counted_stale": _n("stale"),
        "counted_dead": _n("dead"),
        "status_equivalence": STATUS_EQUIVALENCE,
    }


def is_registered(category: str, source_name: str, reg_keys: set[tuple[str, str]]) -> bool:
    """某 (category, source) 是否仍在采集器注册表里。"""
    return (str(category), str(source_name)) in reg_keys


__all__ = [
    "STATUS_EQUIVALENCE",
    "build_census",
    "is_registered",
    "registry_snapshot",
    "stats_snapshot",
]

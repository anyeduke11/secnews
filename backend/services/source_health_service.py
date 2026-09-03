"""v1.7 Phase 4 — 数据源健康判定 (产出趋势版).

PRD §6.10: 数据源健康仪表盘。

与 Phase 9 的 ``source_stats.status`` 区别
-----------------------------------------
- Phase 9 (``source_stats`` 表): 基于 ``zero_yield_runs`` 累计计数判定
  ``active / stale / dead``, 反映 "源是否还活着" (liveness)。
- Phase 4 (本模块): 基于 24h 实际产出 vs 7 天日均的比值判定
  ``green / yellow / red``, 反映 "源当前产出是否偏离基线" (throughput trend)。

两者并存, 互不替代: 一个源可能 Phase 9 = ``active`` (最近一次有产出) 但
Phase 4 = ``yellow`` (24h 产出比 7d 均值下降 40%)。

核心函数
---------
- ``check_health(source)`` — 单个源的健康判定
- ``check_all_health()`` — 所有源的健康判定 (用于仪表盘)

判定算法
---------
::

    recent   = COUNT(hotspots WHERE source=? AND ingested_at >= now-24h)
    baseline = AVG(daily_count) over [now-7d-24h, now-24h)

    if baseline == 0:
        status = "green" if recent > 0 else "red"  # 新源/死源
    else:
        ratio = abs(recent - baseline) / baseline
        status = "green"  if ratio < 0.3
                 "yellow" if ratio < 0.6
                 "red"    otherwise

窗口设计 (与开发计划示例的差异)
---------------------------------
开发计划示例: ``baseline = daily_average(source, days=7)`` 未明确窗口边界.
本实现把 baseline 窗口设为 **[now-7d-24h, now-24h)**, 与 recent 窗口 [now-24h, now]
**不重叠**. 这样:
- "今日产出 vs 过去 7 天日均" 语义清晰
- 新源 (今日刚有产出, 7d 历史为空) 的 baseline == 0, 不会被今日产出污染

偏差说明 (与开发计划 Step 1 代码示例的差异)
---------------------------------------------
开发计划示例: ``if baseline == 0: status = "red"``.
本实现细分:
- ``baseline == 0 AND recent > 0`` → ``green`` (新源刚启动, 正在产出)
- ``baseline == 0 AND recent == 0`` → ``red`` (确实无任何产出历史)

这样更符合 "状态准确" 验收标准, 避免把新加入的工作源误判为 red。

时区
----
- ``ingested_at`` 以 ISO 8601 UTC 字符串存储 (见 migration 007).
- 24h / 7d 窗口基于 UTC ``now``, 与 ``hotspots.ingested_at`` 口径一致。

验收 3: "数据源健康状态准确 (green/yellow/red)"
  → 给定源在 24h 产出与 7d 均值偏差 < 30% 时返回 green,
    偏差 30-60% 返回 yellow, 偏差 >= 60% 返回 red.

P1.7 — 失败率聚合 (failure_rate 信号)
--------------------------------------
新增 ``check_failure_rate_health(source_id)`` —— 基于 ``crawler_runs`` 表
最近 24h 内 ``failed_runs / total_runs`` 的比值判定 ``green/yellow/red``:

- 0 次跑 (新源/无活动)  → green (无信号 = 默认通过)
- 失败率 < 30%          → green
- 失败率 30%-60%        → yellow
- 失败率 >= 60%         → red

与 ``check_health`` 的吞吐趋势信号**正交**: 源可吞吐正常但连续失败 (yellow),
也可吞吐下降但单次都成功 (yellow on trend only).
``check_all_health`` 返回 ``{trend_status, failure_rate_status, status}`` —
``status`` 取两者最差 (red > yellow > green).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.repository.db import get_connection

# 时区: UTC (与 hotspots.ingested_at 存储口径一致)
_UTC = timezone.utc

# 健康阈值 (与开发计划一致)
_RATIO_GREEN = 0.3   # < 30% 偏差 → green
_RATIO_YELLOW = 0.6  # < 60% 偏差 → yellow, 否则 red

# 窗口
_RECENT_HOURS = 24
_BASELINE_DAYS = 7

# P1.7 — failure_rate 阈值 (与 source_alerter Rule 3 / observability_thresholds
# 的 0.3 一致, 但扩展成三档颜色而非二值触发)
_FAILURE_GREEN = 0.3   # failed/total < 30% → green
_FAILURE_YELLOW = 0.6  # failed/total < 60% → yellow, 否则 red
_MIN_RUNS_FOR_SIGNAL = 3  # 至少 3 次运行才计算 (避免 1/1=100% 误判)


def _now_utc() -> datetime:
    return datetime.now(_UTC)


def _count_in_window(source: str, since: datetime, until: datetime | None = None) -> int:
    """统计 source 在 [since, until) 窗口内的 hotspots 行数.

    Parameters
    ----------
    source:
        数据源名.
    since:
        窗口起点 (含).
    until:
        窗口终点 (不含). ``None`` 表示无上界。
    """
    conn = get_connection()
    if until is None:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM hotspots "
            "WHERE source = ? AND ingested_at >= ?",
            (source, since.isoformat()),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM hotspots "
            "WHERE source = ? AND ingested_at >= ? AND ingested_at < ?",
            (source, since.isoformat(), until.isoformat()),
        ).fetchone()
    return int(row["n"]) if row else 0


def _daily_average(source: str, days: int = _BASELINE_DAYS) -> float:
    """计算 source 过去 N 天 (不含最近 24h) 的日均产出.

    baseline 窗口 = [now - N days - 24h, now - 24h), 与 recent 窗口 [now-24h, now]
    不重叠. 这样 "新源" (今日刚有产出) 的 baseline == 0, 不会被今日产出污染.

    Returns
    -------
    float
        日均产出数 = 窗口内总产出 / N. 若窗口内无任何产出, 返回 0.0.
    """
    now = _now_utc()
    baseline_end = now - timedelta(hours=_RECENT_HOURS)
    baseline_start = baseline_end - timedelta(days=days)
    total = _count_in_window(source, baseline_start, baseline_end)
    if total == 0:
        return 0.0
    return float(total) / float(days)


def check_health(source: str) -> dict:
    """判定单个数据源的健康状态 (基于 24h 产出 vs 7d 日均).

    Parameters
    ----------
    source:
        数据源名 (``hotspots.source`` 字段值, 如 ``"freebuf"``).

    Returns
    -------
    dict
        ``{"source", "status", "trend_status", "failure_rate_status",
        "recent_24h", "baseline_7d_avg", "ratio", "failed_runs", "total_runs"}``
        - ``status`` ∈ ``{"green", "yellow", "red"}`` (trend 与 failure_rate 综合最差)
        - ``trend_status`` 单独吞吐趋势判定
        - ``failure_rate_status`` 单独失败率判定
    """
    now = _now_utc()
    recent_since = now - timedelta(hours=_RECENT_HOURS)
    recent = _count_in_window(source, recent_since)
    baseline = _daily_average(source, _BASELINE_DAYS)

    if baseline == 0:
        # 无 7d 历史: 看 24h 是否有产出
        trend_status = "green" if recent > 0 else "red"
        ratio: float | None = None
    else:
        ratio = abs(recent - baseline) / baseline
        if ratio < _RATIO_GREEN:
            trend_status = "green"
        elif ratio < _RATIO_YELLOW:
            trend_status = "yellow"
        else:
            trend_status = "red"

    # P1.7: 失败率信号 (来自 crawler_runs, source_id 格式 {category}:{name_slug})
    failure_info = _failure_rate_for_source_name(source)
    failure_rate_status = failure_info["status"]

    # 综合 = trend 与 failure_rate 取最差 (red > yellow > green)
    severity = {"red": 0, "yellow": 1, "green": 2}
    combined_status = trend_status if severity[trend_status] <= severity[failure_rate_status] else failure_rate_status

    return {
        "source": source,
        "status": combined_status,
        "trend_status": trend_status,
        "failure_rate_status": failure_rate_status,
        "recent_24h": recent,
        "baseline_7d_avg": round(baseline, 3),
        "ratio": round(ratio, 3) if ratio is not None else None,
        "failed_runs": failure_info["failed_runs"],
        "total_runs": failure_info["total_runs"],
        "checked_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# P1.7 — 失败率聚合
# ---------------------------------------------------------------------------
def _failure_rate_for_source_name(source_name: str) -> dict:
    """按 hotspots.source 名 (人类可读) 反查 crawler_runs.source_id 计算 24h 失败率.

    hotspots.source 与 crawler_sources.id 的口径不同: 前者是 name,
    后者是 ``{category}:{name_slug}``. 这里用 name 反查 source_id 列表
    (同名源可能跨多 category), 聚合失败率。

    Returns
    -------
    dict
        ``{"status", "failed_runs", "total_runs", "failure_rate"}``
        - ``status`` ∈ ``{"green", "yellow", "red"}``
    """
    conn = get_connection()
    # 反查: name → 可能多条 (跨 category)
    rows = conn.execute(
        "SELECT id FROM crawler_sources WHERE name = ?",
        (source_name,),
    ).fetchall()
    if not rows:
        # 未在 crawler_sources 注册: 无 failure_rate 信号 → green
        return {
            "status": "green",
            "failed_runs": 0,
            "total_runs": 0,
            "failure_rate": 0.0,
        }
    ids = [r["id"] for r in rows]
    placeholders = ",".join("?" for _ in ids)
    row = conn.execute(
        f"""
        SELECT
          COUNT(*) AS total_runs,
          COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_runs
        FROM crawler_runs
        WHERE source_id IN ({placeholders})
          AND started_at >= datetime('now', '-24 hours')
        """,
        ids,
    ).fetchone()
    total_runs = int(row["total_runs"])
    failed_runs = int(row["failed_runs"])
    if total_runs < _MIN_RUNS_FOR_SIGNAL:
        # 样本不足: 无信号 → green (避免 1/1=100% 误判)
        return {
            "status": "green",
            "failed_runs": failed_runs,
            "total_runs": total_runs,
            "failure_rate": 0.0,
        }
    failure_rate = failed_runs / total_runs
    if failure_rate >= _FAILURE_YELLOW:
        status = "red"
    elif failure_rate >= _FAILURE_GREEN:
        status = "yellow"
    else:
        status = "green"
    return {
        "status": status,
        "failed_runs": failed_runs,
        "total_runs": total_runs,
        "failure_rate": round(failure_rate, 4),
    }


def check_failure_rate_health(source_id: str) -> dict:
    """按 crawler_sources.id 直接查询 24h 失败率 (供需要 source_id 的入口使用).

    与 ``_failure_rate_for_source_name`` 的差别: 接收 ``source_id``
    (crawler v2 内部), 不做 name → id 反查.

    Returns
    -------
    dict
        ``{"source_id", "status", "failed_runs", "total_runs", "failure_rate"}``
    """
    conn = get_connection()
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS total_runs,
          COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_runs
        FROM crawler_runs
        WHERE source_id = ?
          AND started_at >= datetime('now', '-24 hours')
        """,
        (source_id,),
    ).fetchone()
    total_runs = int(row["total_runs"])
    failed_runs = int(row["failed_runs"])
    if total_runs < _MIN_RUNS_FOR_SIGNAL:
        status = "green"
        failure_rate = 0.0
    else:
        failure_rate = failed_runs / total_runs
        if failure_rate >= _FAILURE_YELLOW:
            status = "red"
        elif failure_rate >= _FAILURE_GREEN:
            status = "yellow"
        else:
            status = "green"
    return {
        "source_id": source_id,
        "status": status,
        "failed_runs": failed_runs,
        "total_runs": total_runs,
        "failure_rate": round(failure_rate, 4),
    }


def list_all_sources() -> list[str]:
    """返回 hotspots 表中所有不同的 source 名 (按字母序)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT source FROM hotspots ORDER BY source ASC"
    ).fetchall()
    return [r["source"] for r in rows if r["source"]]


def check_all_health() -> list[dict]:
    """对所有数据源逐一判定健康状态.

    Returns
    -------
    list[dict]
        每个源一个 ``check_health`` 结果, 按 status 严重度排序
        (red > yellow > green), 同 status 按 source 字母序.
    """
    sources = list_all_sources()
    results = [check_health(s) for s in sources]
    # 排序: red > yellow > green, 同 status 按 source
    severity = {"red": 0, "yellow": 1, "green": 2}
    results.sort(key=lambda x: (severity.get(x["status"], 3), x["source"]))
    return results


def health_summary() -> dict:
    """所有源的健康汇总 (用于仪表盘顶部 KPI).

    Returns
    -------
    dict
        ``{"total", "green", "yellow", "red", "checked_at"}``
    """
    items = check_all_health()
    counts = {"green": 0, "yellow": 0, "red": 0}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    return {
        "total": len(items),
        "green": counts["green"],
        "yellow": counts["yellow"],
        "red": counts["red"],
        "checked_at": _now_utc().isoformat(),
    }


__all__ = [
    "check_all_health",
    "check_health",
    "check_failure_rate_health",
    "health_summary",
    "list_all_sources",
]

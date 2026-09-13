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
from backend.repository.db import get_connection, knowledge_items_table
from backend.services.kl_state_machine import LIFECYCLE_DEDUPED


def _lifecycle_sql() -> str:
    """lifecycle 分布 SQL — 运行时经 knowledge_items_table() 解析表名。

    (原为模块级常量 ``_LIFECYCLE_SQL`` 硬编码 ``warm.`` 前缀; 常量在 import
    期求值无法走 accessor — accessor 需按调用线程已 ATTACH 的 schema 判定,
    且 import 期开连接是副作用。改函数后 SQL 文本运行期逐字不变, 单库
    (未 ATTACH warm) 模式下由裸名正确解析到 main。)
    """
    return (
        "SELECT COALESCE(lifecycle, '') AS lifecycle, COUNT(*) AS c "
        f"FROM {knowledge_items_table()} GROUP BY lifecycle"
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
        ``[{"stage": "kl:raw", "count": n}, ..., {"stage": "kl:deduped", "count": d},
        {"stage": "unknown", "count": m}]``
        (stage 顺序与 STAGES 一致 + 终态 ``kl:deduped`` 单列; 值域外/历史值经
        _LEGACY_TO_STAGE 归一, 归不进去的进 unknown, 与 funnel_stats 语义对齐)
    """
    counts: dict[str, int] = dict.fromkeys(STAGES, 0)
    # kl:deduped 单列: 它是 T1 判重项的真实终态。若落进 unknown, 看板会把
    # "已判定重复"显示成"状态未知", 正好掩盖刚建立的可审计性。
    counts[LIFECYCLE_DEDUPED] = 0
    counts[UNKNOWN_STAGE] = 0
    try:
        rows = (conn or get_connection()).execute(_lifecycle_sql()).fetchall()
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
        rows = (conn or get_connection()).execute(_lifecycle_sql()).fetchall()
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
            f"SELECT COUNT(*) FROM {knowledge_items_table()}"
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


# ---------------------------------------------------------------------------
# KL 观测只读查询 (Batch 2 D: api 层 SQL 下沉落点 —
# kl_pipeline_api / kl_metrics_api / mcp_phase5_tools / kl_compounding_api)
# ---------------------------------------------------------------------------
def token_ledger_summary() -> dict[str, Any]:
    """KL token 台账汇总 (kl_pipeline.obs.ledger.TokenLedger)。

    连接线程亲和: 调用方须在 worker 线程内调用 (与 funnel_from_db 同纪律)。
    异常向上抛, 由调用方决定降级语义 (kl_status 503 / pipeline_stats 透传)。
    """
    from backend.kl_pipeline.obs.ledger import TokenLedger

    return TokenLedger(get_connection()).summary()


def kl_stage_counts() -> dict[str, int] | None:
    """KL 各 lifecycle stage 的条目计数 (knowledge_items 直查, ALL_STAGES 域)。

    Returns: stage → count;查询失败返回 None (调用方保持 gauge 旧值,
    与原 kl_metrics_api 的 best-effort 语义一致)。
    """
    from backend.services.kl_state_machine import ALL_STAGES

    try:
        conn = get_connection()
        rows = conn.execute(
            f"SELECT lifecycle, COUNT(*) FROM {knowledge_items_table()} "
            "WHERE lifecycle IN ({}) "
            "GROUP BY lifecycle".format(",".join("?" for _ in ALL_STAGES)),
            tuple(ALL_STAGES),
        ).fetchall()
    except Exception:
        # The gauge is best-effort; never fail the snapshot.
        return None
    counts = dict.fromkeys(ALL_STAGES, 0)
    for stage, n in rows:
        if stage in counts:
            counts[stage] = int(n)
    return counts


# 复利仪表盘 30s TTL 缓存 — 判断层 rail 常驻消费, 每次全量跑 5 组聚合
# (top_concepts 还是 CROSS JOIN json_each 全表展开)。当前 knowledge_items
# ~3800 行便宜, 行数增长后是稳定热点。并发首算可能双写 — last-wins,
# payload 幂等, 无需加锁。
_COMPOUNDING_TTL_S = 30.0
_compounding_cache: tuple[float, dict] | None = None  # (monotonic ts, payload)


def _to_score(val: float | None) -> float:
    """Convert nullable AVG result to float."""
    return round(val, 4) if val is not None else 0.0


def compounding_snapshot() -> dict[str, Any]:
    """复利仪表盘聚合指标 (30s TTL 缓存) — GET /api/kl/compounding 数据面。

    P3-5 数据源口径 (见 api 层历史注释):
    1. avg_score 用 attention_score (真实注意力数据), 不再用 mastery (全 0)
    2. trigger_health 读 kl_dead_letters 表 (持久化) + 进程内计数合并
    3. top_concepts 直接聚合 knowledge_items.concepts 列
    """
    global _compounding_cache

    now = time.monotonic()
    if _compounding_cache is not None and now - _compounding_cache[0] < _COMPOUNDING_TTL_S:
        return _compounding_cache[1]

    conn = get_connection()

    # ── Daily trend (last 30 days) ──────────────────────────────
    # P3-5: avg_score 改用 attention_score (真实注意力数据), 不再用 mastery (全 0)
    daily = conn.execute(
        f"""
        SELECT DATE(ingested_at) AS day,
               COUNT(*) AS count,
               AVG(CAST(attention_score AS REAL)) AS avg_score
        FROM {knowledge_items_table()}
        WHERE ingested_at >= DATE('now', '-30 days')
        GROUP BY day
        ORDER BY day ASC
        """
    ).fetchall()

    # ── Weekly trend (last 12 weeks) ────────────────────────────
    weekly = conn.execute(
        f"""
        SELECT strftime('%Y-W%W', ingested_at) AS week,
               COUNT(*) AS count,
               AVG(CAST(attention_score AS REAL)) AS avg_score
        FROM {knowledge_items_table()}
        WHERE ingested_at >= DATE('now', '-84 days')
        GROUP BY week
        ORDER BY week ASC
        """
    ).fetchall()

    # ── Monthly trend (last 6 months) ───────────────────────────
    monthly = conn.execute(
        f"""
        SELECT strftime('%Y-%m', ingested_at) AS month,
               COUNT(*) AS count,
               AVG(CAST(attention_score AS REAL)) AS avg_score
        FROM {knowledge_items_table()}
        WHERE ingested_at >= DATE('now', '-6 months')
        GROUP BY month
        ORDER BY month ASC
        """
    ).fetchall()

    # ── Top 10 concepts by item participation ───────────────────
    # P3-5: 直接聚合 knowledge_items.concepts (不再依赖稀疏的 knowledge_links)
    top_concepts = conn.execute(
        f"""
        SELECT c.value AS name, COUNT(*) AS score
        FROM {knowledge_items_table()} ki
        CROSS JOIN json_each(ki.concepts) c
        WHERE c.value IS NOT NULL AND c.value != ''
        GROUP BY c.value
        ORDER BY score DESC
        LIMIT 10
        """
    ).fetchall()

    # ── Trigger health ──────────────────────────────────────────
    # P3-5: 死信从 kl_dead_letters 表读 (持久化, 重启不丢), 进程内计数仅补充
    try:
        dl_rows = conn.execute(
            "SELECT trigger_name, COUNT(*) AS n FROM kl_dead_letters "
            "WHERE status = 'active' GROUP BY trigger_name"
        ).fetchall()
        dead_letter_db = {r[0]: r[1] for r in dl_rows}
    except Exception:
        dead_letter_db = {}
    from backend.metrics.kl_metrics import kl_metrics

    counters = kl_metrics.snapshot()["counters"]
    trigger_health = {
        "t1_failed": counters.get("t1_failed", 0),
        "t2_failed": counters.get("t2_failed", 0),
        "t3_failed": counters.get("t3_failed", 0),
        "t4_failed": counters.get("t4_failed", 0),
        "dead_letter_count": sum(dead_letter_db.values()),
        "dead_letter_by_trigger": dead_letter_db,
    }

    # ── Stage distribution ──────────────────────────────────────
    stage_rows = conn.execute(
        f"SELECT lifecycle, COUNT(*) FROM {knowledge_items_table()} "
        "WHERE lifecycle IS NOT NULL AND lifecycle != '' "
        "GROUP BY lifecycle ORDER BY COUNT(*) DESC"
    ).fetchall()

    payload = {
        "daily_trend": [
            {"day": r[0], "count": r[1], "avg_score": _to_score(r[2])}
            for r in daily
        ],
        "weekly_trend": [
            {"week": r[0], "count": r[1], "avg_score": _to_score(r[2])}
            for r in weekly
        ],
        "monthly_trend": [
            {"month": r[0], "count": r[1], "avg_score": _to_score(r[2])}
            for r in monthly
        ],
        "top_concepts": [
            {"name": r[0], "score": r[1]} for r in top_concepts
        ],
        "trigger_health": trigger_health,
        "stage_distribution": {r[0]: r[1] for r in stage_rows},
    }
    _compounding_cache = (now, payload)
    return payload


__all__ = [
    "compounding_snapshot",
    "funnel_from_db",
    "invalidate_stats_cache",
    "kl_stage_counts",
    "knowledge_stats_from_db",
    "liveness_from_md_cached",
    "stage_distribution_from_db",
    "token_ledger_summary",
]

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
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.kl_pipeline.obs.funnel import _LEGACY_TO_STAGE, UNKNOWN_STAGE
from backend.kl_pipeline.queue import STAGES
from backend.logging_config import logger
from backend.repository.db import get_connection, knowledge_items_table
from backend.services.kl_state_machine import LIFECYCLE_ARCHIVED, LIFECYCLE_DEDUPED


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
# md 回退漏斗的 TTL 缓存 (2026-09-18): warm.db 遗失后 knowledge_items 投影
# 表不存在, funnel_from_db 对 "no such table" 回退 md 真源; 全量扫描 ~4200
# 文件不能随 30s 轮询每次重扫, 与 liveness 同款 TTL。
_md_funnel_cache: dict[str, tuple[float, list]] = {}

# 区分 "未传 wiki_fs" (缺省抓 production 单例回退) 与 "显式传 None"
# (调用方声明无 md 源 → 保持归零契约, 见 SecNewsDashboard.wiki_fs 注入语义)。
_WIKI_UNSET = object()


def _funnel_counts_from_md(wiki_fs: Any) -> dict[str, int]:
    """md 真源口径的漏斗计数 — 与 DB 口径同归一 (legacy 映射 + deduped 单列)。

    (不复用 kl_pipeline.obs.funnel.funnel_stats: 其 counts 无 kl:deduped 键,
    终态 "已判定重复" 会被错归进 unknown, 恰好掩盖可审计性 — 见
    funnel_from_db 的 deduped 单列注释。)
    """
    from backend.wiki_fs.contract import get_lifecycle

    counts: dict[str, int] = dict.fromkeys(STAGES, 0)
    counts[LIFECYCLE_DEDUPED] = 0
    counts[UNKNOWN_STAGE] = 0
    for item_id in wiki_fs.list_ids():
        doc = wiki_fs.read_item(item_id)
        if doc is None:
            counts[UNKNOWN_STAGE] += 1
            continue
        stage = get_lifecycle(doc["fm"])
        stage = _LEGACY_TO_STAGE.get(stage, stage)
        counts[stage if stage in counts else UNKNOWN_STAGE] += 1
    return counts


def funnel_from_md_cached(
    wiki_fs: Any = None, *, ttl_s: float = _LIVENESS_TTL_S
) -> list[dict[str, Any]]:
    """md 真源漏斗 (DB 投影不可用时的回退), 30s TTL 进程内缓存。

    必须在 worker 线程调用 (与 funnel_from_db 同纪律); wiki_fs 缺省取
    生产单例 (kl_pipeline.runtime.get_production_wiki_fs)。
    """
    now = time.monotonic()
    with _liveness_lock:
        hit = _md_funnel_cache.get("funnel")
        if hit and now - hit[0] < ttl_s:
            return hit[1]

    if wiki_fs is None:
        from backend.kl_pipeline.runtime import get_production_wiki_fs

        wiki_fs = get_production_wiki_fs()
    try:
        counts = _funnel_counts_from_md(wiki_fs)
    except Exception as e:
        logger.warning(f"funnel md fallback failed: {e}")
        counts = dict.fromkeys(STAGES, 0)
        counts[LIFECYCLE_DEDUPED] = 0
        counts[UNKNOWN_STAGE] = 0
    result = [{"stage": s, "count": c} for s, c in counts.items()]
    with _liveness_lock:
        _md_funnel_cache["funnel"] = (time.monotonic(), result)
    return result


# ---------------------------------------------------------------------------
# funnel / stage 分布 — DB 投影 (warm.knowledge_items.lifecycle)
# ---------------------------------------------------------------------------
def funnel_from_db(conn: Any = None, *, wiki_fs: Any = _WIKI_UNSET) -> list[dict[str, Any]]:
    """管线漏斗 — 从 DB 投影统计, 与 md 归档口径的差异见模块 docstring。

    Args:
        conn: 可注入连接 (测试/调用方持有 thread-local 连接时传 self.db);
            缺省用 get_connection()。
        wiki_fs: 投影查询失败时的 md 回退源。未传 → 缺省抓 production 单例
            (独立调用方如 kl_pipeline_api 的缺省行为); **显式传 None → 禁用
            回退**, 返回全 0 (SecNewsDashboard(wiki_fs=None) 的注入契约:
            调用方声明无 md 源, 与 liveness 降级语义一致)。

    Returns:
        ``[{"stage": "kl:raw", "count": n}, ..., {"stage": "kl:deduped", "count": d},
        {"stage": "kl:archived", "count": a}, {"stage": "unknown", "count": m}]``
        (stage 顺序与 STAGES 一致 + 终态 ``kl:deduped``/``kl:archived`` 单列; 值域外/
        历史值经 _LEGACY_TO_STAGE 归一, 归不进去的进 unknown, 与 funnel_stats 语义对齐)
    """
    counts: dict[str, int] = dict.fromkeys(STAGES, 0)
    # kl:deduped 单列: 它是 T1 判重项的真实终态。若落进 unknown, 看板会把
    # "已判定重复"显示成"状态未知", 正好掩盖刚建立的可审计性。
    counts[LIFECYCLE_DEDUPED] = 0
    # kl:archived 单列 (DEV-0241): wiki_archiver 兜底物化终态 — 归档 ≠ 已发布
    # 知识, 落进 unknown 会把"归档存量"显示成"状态未知"。
    counts[LIFECYCLE_ARCHIVED] = 0
    counts[UNKNOWN_STAGE] = 0
    try:
        rows = (conn or get_connection()).execute(_lifecycle_sql()).fetchall()
    except Exception as e:
        # DB 投影缺失 (2026-09-18 warm.db 遗失 → knowledge_items 表不存在)
        # 不再静默返回全 0 — 回退 md 归档口径让漏斗保持可读 (注意: md 数字
        # 与 DB 管线口径本就不同, 此为降级展示而非口径替换, 日志留痕)。
        # 显式注入 wiki_fs=None 时调用方已声明无 md 源 → 保持归零契约。
        logger.warning(f"funnel_from_db query failed, falling back to md source: {e}")
        if wiki_fs is None:
            return [{"stage": s, "count": 0} for s in counts]
        return funnel_from_md_cached(None if wiki_fs is _WIKI_UNSET else wiki_fs)

    if not rows:
        # 终审 Important 修复 (2026-09-26): db.py 自愈建空 knowledge_items 后
        # 查询成功返回 0 行不再抛异常 — 静默返回全 0 会把看板存量从 4179 断层
        # 成 0 (缺表走上方 except 反而显示 md 真实数)。空集视为投影未回填,
        # 与缺表同回退 md 口径 (降级展示, 回填后自动恢复 DB 口径)。
        logger.warning("warm 投影空 (knowledge_items 0 行), 已回退 md 口径, 建议跑回填")
        if wiki_fs is None:
            return [{"stage": s, "count": 0} for s in counts]
        return funnel_from_md_cached(None if wiki_fs is _WIKI_UNSET else wiki_fs)

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


def stage_distribution_from_db(
    conn: Any = None, *, wiki_fs: Any = _WIKI_UNSET
) -> dict[str, int]:
    """知识库 tab 的 lifecycle 分布 (同 funnel 数据源, dict 形态)。

    wiki_fs 参数语义同 funnel_from_db: 未传 → 回退抓 production 单例;
    显式 None → 禁用回退, 投影缺失时保持原 ``{}`` 归零契约。
    """
    dist: dict[str, int] = {}
    try:
        rows = (conn or get_connection()).execute(_lifecycle_sql()).fetchall()
    except Exception as e:
        logger.warning(
            f"stage_distribution_from_db query failed, falling back to md source: {e}"
        )
        if wiki_fs is None:
            return dist
        return {
            f["stage"]: f["count"]
            for f in funnel_from_md_cached(None if wiki_fs is _WIKI_UNSET else wiki_fs)
        }
    if not rows:
        # 终审 Important 修复 (2026-09-26): 空投影同 funnel_from_db 回退 md
        # (knowledge_stats 的 stage_distribution 依赖本函数, 不回退则知识库
        # tab 分布在空表下断层为空 dict)。
        logger.warning("warm 投影空 (knowledge_items 0 行), 已回退 md 口径, 建议跑回填")
        if wiki_fs is None:
            return dist
        return {
            f["stage"]: f["count"]
            for f in funnel_from_md_cached(None if wiki_fs is _WIKI_UNSET else wiki_fs)
        }
    for row in rows:
        stage = (row["lifecycle"] or "").strip() or "unknown"
        dist[stage] = dist.get(stage, 0) + row["c"]
    return dist


def knowledge_stats_from_db(
    conn: Any = None, *, wiki_fs: Any = _WIKI_UNSET
) -> dict[str, Any]:
    """知识库统计 (条目数/概念数/生命周期分布) — 全部走 DB, 零文件 IO。

    wiki_fs 透传给 stage_distribution_from_db (投影缺失时的 md 回退源;
    SecNewsDashboard 按自身注入传 self.wiki_fs, None 即禁用回退)。
    """
    items = 0
    concepts = 0
    conn = conn or get_connection()
    # items 与 concepts 分开容错: warm.knowledge_items (投影, 2026-09-18 遗失)
    # 缺失不应连坐 main.knowledge_concepts (HOT 本地表, warm 遗失时仍健在)。
    try:
        items = conn.execute(
            f"SELECT COUNT(*) FROM {knowledge_items_table()}"
        ).fetchone()[0]
    except Exception as e:
        logger.warning(f"knowledge_stats_from_db items query failed: {e}")
        items = 0
    if not items and wiki_fs is not None:
        # 投影缺失或空表 (终审 Important 修复: 自愈建空壳后 COUNT=0 不抛异常)
        # → 回退 md 条目总数 (与漏斗回退共享 30s TTL 缓存, 零额外扫描)。
        logger.warning("warm 投影空 (knowledge_items 0 行), 已回退 md 口径, 建议跑回填")
        funnel = funnel_from_md_cached(None if wiki_fs is _WIKI_UNSET else wiki_fs)
        items = sum(f["count"] for f in funnel)
    try:
        concepts = conn.execute(
            "SELECT COUNT(*) FROM knowledge_concepts"
        ).fetchone()[0]
    except Exception as e:
        logger.warning(f"knowledge_stats_from_db concepts query failed: {e}")
    return {
        "items": items,
        "concepts": concepts,
        "stage_distribution": stage_distribution_from_db(conn, wiki_fs=wiki_fs),
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
    """wiki 写入方 (kl管线/导入) 可调用: 清掉 liveness/md 漏斗缓存让下一请求重扫。"""
    with _liveness_lock:
        _liveness_cache.clear()
        _md_funnel_cache.clear()


# ---------------------------------------------------------------------------
# KL 吞吐 — wiki_events kl_transition 事件流聚合 (治理 T3 漏斗改吞吐视图)
# ---------------------------------------------------------------------------
_THROUGHPUT_WINDOW_DAYS = 7

# kl_transition 生产写点 = T1-T4 触发器 + kl_queue drain, 但两来源 payload.stage
# 语义不同: engine drain 写**刚完成阶段**, trigger 写**到达阶段** — 各来源内
# 自洽, 混合聚合是近似吞吐 (更精确需按 item 对齐前后沿, 当前 payload 无 item_id,
# 接受近似)。
# kl:raw 无任何写点 (kickoff 直接入队 kl:refine, 不写事件) — 保留恒 0 键会让
# 前端 raw 行永久显示 0 流量 (停摆黄条误报帮凶), 吞吐值域 = STAGES 去 kl:raw。
_THROUGHPUT_STAGES = STAGES[1:]

# kl_transition payload.stage 的到达配对 (进阶转化率), 首跳 kl:raw 无写点故无配对
_CONVERSION_PAIRS = (
    ("refine", "link"),
    ("link", "structure"),
    ("structure", "publish"),
)


def kl_transition_throughput(
    conn: Any = None, *, days: int = _THROUGHPUT_WINDOW_DAYS
) -> dict[str, Any]:
    """近 N 天管线吞吐 — wiki_events ``kl_transition`` 事件流聚合 (治理 T3)。

    与 :func:`funnel_from_db` (存量快照) 的口径区别: 快照回答"现在各阶段
    躺了多少条", 吞吐回答"最近流动了多少"。2026-09 实测 publish 存量
    4179 条 vs 近 7 天流动 0 条 — 管线停摆 13 天, 快照却依然"看起来健康",
    唯有流量口径能暴露停摆 (前端停摆黄条的数据面)。

    事件写点 (治理 T4 review fix 起齐全): T1-T4 触发器推进 (payload.stage=
    到达阶段) + kl_queue drain — 生产复活链从此计入吞吐与 last_transition_at。

    Args:
        conn: 可注入连接 (测试); 缺省 get_connection()。
        days: 吞吐统计窗口 (默认 7 天); last_transition_at 不受窗口限制。

    Returns:
        ``{"throughput_7d": {stage: count}, "conversion": {prev_to_next: rate|None},
        "last_transition_at": iso|None}``
        throughput_7d 值域 = STAGES 去 kl:raw (kl:raw 无事件写点, 恒 0 键已移除);
        last_transition_at 同排除 kl:deduped 判重心跳 (上游喂重复不算知识流动);
        conversion 前项到达量为 0 时该比率为 None (除零不编造);
        wiki_events 查询失败 (表缺失等) → 归零结构, 不炸看板。
    """
    conn = conn or get_connection()
    out: dict[str, Any] = {
        "throughput_7d": dict.fromkeys(_THROUGHPUT_STAGES, 0),
        "conversion": {},
        "last_transition_at": None,
    }
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat()
    try:
        rows = conn.execute(
            "SELECT json_extract(payload, '$.stage') AS stage, COUNT(*) AS c "
            "FROM wiki_events "
            "WHERE kind = 'kl_transition' AND ts >= ? "
            "GROUP BY stage",
            (cutoff,),
        ).fetchall()
        last = conn.execute(
            "SELECT MAX(ts) FROM wiki_events WHERE kind = 'kl_transition' "
            # 终审 Minor 修复: 排除 kl:deduped 心跳 — T1 判重落终态也写
            # kl_transition, 上游持续喂重复 item 会不断刷新最后心跳,
            # 停摆黄条把 "喂重复" 误判成 "知识在流动"。
            "AND COALESCE(json_extract(payload, '$.stage'), '') != 'kl:deduped'"
        ).fetchone()
    except Exception as e:
        logger.warning(f"kl_transition_throughput query failed: {e}")
        return out
    for row in rows:
        stage = (row["stage"] or "").strip()
        if stage in out["throughput_7d"]:
            out["throughput_7d"][stage] = int(row["c"])
    out["last_transition_at"] = last[0] if last is not None else None
    tp: dict[str, int] = out["throughput_7d"]
    out["conversion"] = {
        f"{prev}_to_{nxt}": (
            round(tp[f"kl:{nxt}"] / tp[f"kl:{prev}"], 4) if tp[f"kl:{prev}"] else None
        )
        for prev, nxt in _CONVERSION_PAIRS
    }
    return out


# ---------------------------------------------------------------------------
# pipeline/stats 组装 (治理 T3 review fix: api 层只留薄转发, 组装下沉 service)
# ---------------------------------------------------------------------------
def pipeline_stats_snapshot(pipeline: Any, wiki_fs: Any) -> dict[str, Any]:
    """GET /api/kl/pipeline/stats 的完整数据面 (漏斗 + 吞吐 + 队列 + 台账)。

    连接线程亲和: funnel/throughput/queue/ledger 的 ``get_connection`` 均在
    本函数内执行, 调用方必须在 worker 线程内调用 (端点侧 ``asyncio.to_thread``,
    与 funnel_from_db 同纪律, 见 v0.6.3 P0-1 卡顿根治), 不在事件循环上直跑。
    """
    funnel = funnel_from_db()
    throughput = kl_transition_throughput()
    queue_stats = pipeline.queue.stats()
    errors = pipeline.queue.errors(limit=10)
    ledger = token_ledger_summary()
    alive = liveness_from_md_cached(wiki_fs)
    return {
        "funnel": funnel,
        "funnel_source": "db_knowledge_items_lifecycle",
        "funnel_counts_items": sum(int(f.get("count") or 0) for f in funnel),
        "funnel_note": "按 DB warm.knowledge_items.lifecycle 统计 (T1-T5 管线真实口径, 与 md 归档数字不同)",
        # 治理 T3: 吞吐口径 (近 7d kl_transition 事件流 + 转化率 + 最后心跳) —
        # 存量快照被 T4 直灌污染时只有流量能暴露停摆; funnel 为存量语义, 向后兼容保留。
        "throughput": throughput,
        "throughput_note": "throughput_7d=近7天各阶段 kl_transition 到达量 (流量口径); last_transition_at 供停摆判定",
        "queue": queue_stats,
        "queue_source": "kl_queue_table",
        "queue_note": "待处理任务队列, 非全量条目数",
        "errors": errors,
        "alive": alive,
        "ledger": ledger,
    }


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
    "funnel_from_md_cached",
    "invalidate_stats_cache",
    "kl_stage_counts",
    "kl_transition_throughput",
    "knowledge_stats_from_db",
    "liveness_from_md_cached",
    "pipeline_stats_snapshot",
    "stage_distribution_from_db",
    "token_ledger_summary",
]

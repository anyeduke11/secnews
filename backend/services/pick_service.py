"""精选评分服务 (2026-09-27 四模式重定义 P2, spec §3)。

pick_score = quality_score
           + (interest_boost - 1) × 25        (关注域, ∈[-5, +7.5])
           + 10 × favored_source               (收藏 ≥2 篇的源)
           × 时效衰减系数 (≤24h: 1.0; 24h~168h: 线性降至 0.6)

每轮 post-ingest 对窗口内新条目计算, Top-N 落 pick_score 列, 其余置 NULL
(视图 COALESCE(pick_score, quality_score) 排序)。纯规则无 LLM。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# 时效衰减
FULL_WEIGHT_HOURS = 24
DECAY_FLOOR_HOURS = 168  # 7d
DECAY_FLOOR = 0.6

# 加权
INTEREST_SPAN = 25     # (boost-1) 的放大系数
FAVORED_SOURCE_BONUS = 10.0

_TOP_N_DEFAULT = 30
_SETTINGS_KEY_TOPN = "quality.pick_top_n"


def compute_pick_score(
    *,
    quality_score: float,
    interest_boost: float,
    favored_source: bool,
    fetched_at_iso: str,
) -> float:
    """单条合成 (纯函数)。boost/favored 参数由调用方批量预取。"""
    base = float(quality_score or 60)
    interest = (float(interest_boost) - 1.0) * INTEREST_SPAN
    favored = FAVORED_SOURCE_BONUS if favored_source else 0.0

    try:
        fetched = datetime.fromisoformat(fetched_at_iso)
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
    except Exception:
        hours = 0.0

    if hours <= FULL_WEIGHT_HOURS:
        decay = 1.0
    elif hours >= DECAY_FLOOR_HOURS:
        decay = DECAY_FLOOR
    else:
        span = DECAY_FLOOR_HOURS - FULL_WEIGHT_HOURS
        decay = 1.0 - (hours - FULL_WEIGHT_HOURS) / span * (1.0 - DECAY_FLOOR)

    return round((base + interest + favored) * decay, 2)


def _load_boost_map() -> dict[str, float]:
    """关注域乘子 (interest_engine 既有缓存)。失败 → 空 (无加成)。"""
    try:
        from backend.services.interest_engine_service import InterestEngineService

        return InterestEngineService().get_boost_map()
    except Exception:
        return {}


def _load_favored_sources(min_count: int = 2) -> set[str]:
    """收藏 ≥min_count 篇的源集合。失败 → 空。"""
    try:
        from backend.repository.db import get_connection

        rows = get_connection().execute(
            "SELECT h.source, COUNT(*) c FROM favorites f "
            "JOIN hotspots h ON f.hotspot_id = h.id "
            "GROUP BY h.source HAVING c >= ?",
            (min_count,),
        ).fetchall()
        return {r["source"] for r in rows}
    except Exception:
        return set()


def _load_top_n() -> int:
    try:
        from backend.repository.settings_repo import SettingsRepository

        v = SettingsRepository().get(_SETTINGS_KEY_TOPN, default=None)
        if isinstance(v, (int, float)) and int(v) > 0:
            return int(v)
    except Exception:
        pass
    return _TOP_N_DEFAULT


def refresh_pick_scores(
    lookback_hours: int = 40, top_n: int | None = None
) -> dict[str, int]:
    """采集尾部入口: 窗口内新条目算分, Top-N 落列, 其余置 NULL。

    全程不抛 (调用方 _tick 再兜一层)。
    """
    from backend.repository.db import get_connection

    n = top_n if top_n is not None else _load_top_n()
    boost = _load_boost_map()
    favored = _load_favored_sources()

    now_utc = datetime.now(timezone.utc)
    cutoff = (now_utc - timedelta(hours=lookback_hours)).isoformat()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, COALESCE(quality_score, score, 60) qs, source,"
        " category, fetched_at FROM hotspots "
        "WHERE fetched_at >= ? ORDER BY fetched_at DESC LIMIT 1000",
        (cutoff,),
    ).fetchall()
    if not rows:
        return {"evaluated": 0, "picked": 0}

    scored: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        s = compute_pick_score(
            quality_score=float(item["qs"]),
            interest_boost=float(boost.get(item["category"], 1.0)),
            favored_source=item["source"] in favored,
            fetched_at_iso=item["fetched_at"],
        )
        scored.append({"id": item["id"], "pick_score": s})

    scored.sort(key=lambda x: x["pick_score"], reverse=True)
    picked_ids = {x["id"] for x in scored[:n]}
    by_id = {x["id"]: x["pick_score"] for x in scored}

    for item_id, score in by_id.items():
        val = score if item_id in picked_ids else None
        conn.execute(
            "UPDATE hotspots SET pick_score = ? WHERE id = ?", (val, item_id)
        )
    return {"evaluated": len(scored), "picked": min(n, len(scored))}


__all__ = ["compute_pick_score", "refresh_pick_scores"]

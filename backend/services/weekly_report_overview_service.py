"""WeeklyReportOverviewService — 周报结构化数据生成 (AIHot 风格).

从指定周的热点数据中提取主线条、分类看点及精选文章（每看点 3 篇）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.repository.db import get_connection

logger = logging.getLogger("hotspot.weekly_report_overview_service")

CATEGORY_LABELS: dict[str, str] = {
    "security": "安全",
    "ai": "AI",
    "ai_security": "AI安全",
    "finance": "金融",
    "startup": "创业",
    "bid": "招标",
    "github": "GitHub",
    "tech": "科技",
}

CATEGORY_ORDER = [
    "ai", "security", "ai_security", "tech", "finance",
    "startup", "github", "bid",
]

CATEGORY_SUMMARIES: dict[str, str] = {
    "ai": "AI领域本周模型发布、融资动态和应用落地进展显著。",
    "security": "安全领域漏洞披露、威胁情报和法规更新持续活跃。",
    "ai_security": "AI安全交叉领域本周关注度持续上升。",
    "tech": "科技领域涵盖硬件、云计算、开发者工具和开源项目。",
    "finance": "金融领域关注市场动态、政策变化和行业趋势。",
    "startup": "创业领域融资事件和新兴项目活跃。",
    "github": "GitHub领域热门开源项目和新版本发布密集。",
    "bid": "招标领域本周发布多个重要项目。",
}


def _week_range(week_start_str: str) -> tuple[str, str, str, str]:
    """Parse week_start ISO date and return (start_iso, end_iso, label, vol_label).

    week_start_str: "2026-07-27" (Monday)
    """
    start = datetime.strptime(week_start_str, "%Y-%m-%d")
    end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    # end_of_week 占位 — 备 Phase 后续按周维度做对比 (与上一周对比)
    _end_of_week = start + timedelta(days=6)
    del _end_of_week

    iso = start.isocalendar()
    label = f"{start.year}年W{iso.week:02d}"
    vol_label = f"{start.year}-W{iso.week:02d}"

    return (
        start.isoformat(),
        end.isoformat(),
        label,
        vol_label,
    )


def _fetch_week_data(week_start: str, week_end: str) -> list[dict]:
    """Fetch hotspot items for the given week range."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, title, summary, source, url, category, published_at, ingested_at,
               score, quality_score
        FROM hotspots
        WHERE ingested_at >= ? AND ingested_at < ?
          AND is_fallback = 0
        ORDER BY COALESCE(quality_score, score, 0) DESC
        LIMIT 300
        """,
        (week_start, week_end),
    ).fetchall()
    return [
        {
            "id": r[0],
            "title": r[1],
            "summary": r[2] or "",
            "source": r[3],
            "url": r[4],
            "category": r[5],
            "published_at": r[6],
            "ingested_at": r[7],
            "score": r[8] or 0,
            "quality_score": r[9] or 0,
        }
        for r in rows
    ]


def _group_by_category(items: list[dict]) -> dict[str, list[dict]]:
    """Group items by category."""
    groups: dict[str, list[dict]] = {}
    for item in items:
        cat = item.get("category", "other")
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(item)
    return groups


def _build_main_theme(
    groups: dict[str, list[dict]],
    total: int,
) -> str:
    """Build a ~500 word main theme summary for the week."""
    if not groups:
        return "本周暂无热点资讯。"

    # ── Opening: domain overview ──
    active_labels: list[str] = []
    for cat in CATEGORY_ORDER:
        if cat in groups:
            active_labels.append(CATEGORY_LABELS.get(cat, cat))
    active_str = "、".join(active_labels)

    lines: list[str] = [
        (f"本周共收录{total}篇热点资讯，覆盖{len(groups)}个核心领域"
        f"（{active_str}），各领域资讯活跃度总体保持稳定。")
    ]

    # ── Per-domain analysis ──
    for cat in CATEGORY_ORDER:
        items = groups.get(cat, [])
        if not items:
            continue
        label = CATEGORY_LABELS.get(cat, cat)

        sources = set()
        for item in items:
            s = item.get("source", "")
            if s:
                sources.add(s)
        source_str = f"来自{len(sources)}个来源"

        n = len(items)
        if n >= 10:
            trend = "活跃度较高"
        elif n >= 5:
            trend = "保持稳定更新"
        elif n >= 3:
            trend = "有持续关注"
        else:
            trend = "有少量重要资讯"

        top = items[:3]
        titles = "、".join(
            t["title"][:50] for t in top if t.get("title")
        )

        lines.append(
            f"**{label}**领域本周共收录{n}篇资讯，{source_str}，{trend}。"
            f"重点资讯包括：{titles}等。"
        )

    # ── Closing: ranking & outlook ──
    ranked = sorted(
        [(cat, len(items)) for cat, items in groups.items()],
        key=lambda x: -x[1],
    )
    if ranked:
        first_label = CATEGORY_LABELS.get(ranked[0][0], ranked[0][0])
        closing = (
            f"从数据分布来看，**{first_label}**领域资讯量最为突出"
            f"（{ranked[0][1]}篇）"
        )
        if len(ranked) > 1:
            second_label = CATEGORY_LABELS.get(ranked[1][0], ranked[1][0])
            closing += f"，**{second_label}**领域紧随其后（{ranked[1][1]}篇）"
        closing += (
            "。整体反映出行业持续向智能化、安全化方向演进，"
            "各领域动态值得持续跟踪。"
        )
        lines.append(closing)

    return "\n\n".join(lines)


def _build_highlights(groups: dict[str, list[dict]]) -> list[dict]:
    """Build up to 10 highlights, each with 3 articles."""
    highlighted: list[dict] = []
    for cat in CATEGORY_ORDER:
        items = groups.get(cat, [])
        if not items:
            continue
        label = CATEGORY_LABELS.get(cat, cat)
        top3 = items[:3]
        highlighted.append({
            "id": cat,
            "title": label,
            "count": len(items),
            "summary": _build_category_summary(cat, label, top3),
            "articles": [
                {
                    "id": a["id"],
                    "title": a["title"],
                    "summary": a.get("summary", "")[:200],
                    "source": a.get("source", ""),
                    "url": a.get("url", ""),
                    "score": a.get("quality_score") or a.get("score") or 0,
                }
                for a in top3
            ],
        })
        if len(highlighted) >= 10:
            break
    return highlighted


def _build_category_summary(cat: str, label: str, articles: list[dict]) -> str:
    """Build a short thematic summary for a category highlight."""
    if not articles:
        return ""
    sources = set()
    for a in articles:
        s = a.get("source", "")
        if s:
            sources.add(s)
    sources_str = "、".join(sorted(sources)[:5]) if sources else "多个来源"

    base = CATEGORY_SUMMARIES.get(cat, "")
    detail = (
        f"本周精选{len(articles)}篇代表性文章，"
        f"来自{sources_str}等来源。"
    )
    return f"{base}{detail}" if base else detail


def generate_weekly_overview(week_start: str) -> dict[str, Any]:
    """Generate the weekly overview for a given week start (ISO date).

    Args:
        week_start: ISO date string like "2026-07-27" (Monday).

    Returns structured dict with main_theme, highlights, period, stats.
    """
    start_iso, end_iso, label, vol_label = _week_range(week_start)
    items = _fetch_week_data(start_iso, end_iso)
    total = len(items)
    groups = _group_by_category(items)

    # Category counts
    category_counts: dict[str, int] = {}
    for cat, cat_items in groups.items():
        lbl = CATEGORY_LABELS.get(cat, cat)
        category_counts[lbl] = len(cat_items)

    main_theme = _build_main_theme(groups, total)
    highlights = _build_highlights(groups)

    # Stats: daily reports count = unique days with data
    days_with_data: set[str] = set()
    for item in items:
        ts = item.get("ingested_at") or item.get("published_at") or ""
        if ts:
            days_with_data.add(ts[:10])
    daily_reports = len(days_with_data)

    # Reading time estimate: ~0.5 min per highlight
    reading_time = max(1, round(len(highlights) * 0.5))

    return {
        "period": {
            "label": label,
            "vol": vol_label,
            "start": start_iso,
            "end": end_iso,
            "week_start": week_start,
        },
        "total": total,
        "category_counts": category_counts,
        "main_theme": main_theme,
        "highlights": highlights,
        "stats": {
            "events": total,
            "selected": total,
            "daily_reports": daily_reports,
            "reading_time": reading_time,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def list_available_weeks() -> list[dict]:
    """List weeks that have data available for weekly reports."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT DISTINCT ingested_at
        FROM hotspots
        WHERE is_fallback = 0 AND ingested_at IS NOT NULL
        ORDER BY ingested_at DESC
        """
    ).fetchall()

    # Collect unique ISO weeks
    seen: set[str] = set()
    result: list[dict] = []
    for row in rows:
        ts = row[0]
        if ts is None:
            continue
        try:
            d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            iso = d.isocalendar()
            # Monday of the ISO week
            monday = d - timedelta(days=d.weekday())
            week_key = f"{iso.year}-W{iso.week:02d}"
            if week_key in seen:
                continue
            seen.add(week_key)
            ws = monday.strftime("%Y-%m-%d")
            label = f"{d.year}年W{iso.week:02d}"
            result.append({"value": ws, "label": label, "vol": week_key})
        except (ValueError, AttributeError):
            continue
        if len(result) >= 52:
            break
    return result


__all__ = [
    "generate_weekly_overview",
    "list_available_weeks",
]
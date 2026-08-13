"""DailyReportOverviewService — 日报结构化数据生成 (AIHot 风格).

从当日热点数据中提取主线条、热点分析、分类看点及精选文章。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from backend.repository.db import get_connection

logger = logging.getLogger("hotspot.daily_report_overview_service")

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
    "ai": "AI领域模型发布、融资动态和应用落地进展显著。",
    "security": "安全领域漏洞披露、威胁情报和法规更新持续活跃。",
    "ai_security": "AI安全交叉领域关注度持续上升。",
    "tech": "科技领域涵盖硬件、云计算、开发者工具和开源项目。",
    "finance": "金融领域关注市场动态、政策变化和行业趋势。",
    "startup": "创业领域融资事件和新兴项目活跃。",
    "github": "GitHub领域热门开源项目和新版本发布密集。",
    "bid": "招标领域发布多个重要项目。",
}


def _today_range() -> tuple[str, str, str]:
    """Return (start_iso, end_iso, date_label) for today (Asia/Shanghai)."""
    now = datetime.now(timezone.utc)
    # Convert to Asia/Shanghai for "today"
    shanghai = now + timedelta(hours=8)
    today_start = shanghai.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(hours=23, minutes=59, seconds=59)
    # Convert back to UTC for SQL query
    start_utc = (today_start - timedelta(hours=8)).isoformat()
    end_utc = (today_end - timedelta(hours=8)).isoformat()

    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    wd = weekdays[today_start.weekday()]
    date_label = f"{today_start.year}年{today_start.month}月{today_start.day}日 · 周{wd}"

    return start_utc, end_utc, date_label


def _fetch_today_data(start_iso: str, end_iso: str) -> list[dict]:
    """Fetch hotspot items for today's range."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, title, summary, source, url, category, published_at, ingested_at,
               score, quality_score
        FROM hotspots
        WHERE ingested_at >= ? AND ingested_at < ?
          AND is_fallback = 0
        ORDER BY COALESCE(quality_score, score, 0) DESC
        LIMIT 200
        """,
        (start_iso, end_iso),
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
    """Build a ~500 word main theme summary for today."""
    if not groups:
        return "今日暂无热点资讯。"

    active_labels: list[str] = []
    for cat in CATEGORY_ORDER:
        if cat in groups:
            active_labels.append(CATEGORY_LABELS.get(cat, cat))
    active_str = "、".join(active_labels)

    lines: list[str] = [
        f"今日共收录 **{total}** 篇热点资讯，覆盖 **{len(groups)}** 个核心领域"
        f"（{active_str}），各领域资讯活跃度总体保持稳定。"
    ]

    # Per-domain analysis
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
        source_str = f"来自 **{len(sources)}** 个来源"

        n = len(items)
        if n >= 8:
            trend = "活跃度较高"
        elif n >= 4:
            trend = "保持稳定更新"
        elif n >= 2:
            trend = "有持续关注"
        else:
            trend = "有少量重要资讯"

        top = items[:3]
        titles = "、".join(
            t["title"][:60] for t in top if t.get("title")
        )

        lines.append(
            f"**{label}**领域今日共收录 **{n}** 篇资讯，{source_str}，{trend}。"
            f"重点资讯包括：**{titles}** 等。"
        )

    # Ranking & outlook
    ranked = sorted(
        [(cat, len(items)) for cat, items in groups.items()],
        key=lambda x: -x[1],
    )
    if ranked:
        first_label = CATEGORY_LABELS.get(ranked[0][0], ranked[0][0])
        closing = (
            f"从数据分布来看，**{first_label}** 领域资讯量最为突出"
            f"（**{ranked[0][1]}** 篇）"
        )
        if len(ranked) > 1:
            second_label = CATEGORY_LABELS.get(ranked[1][0], ranked[1][0])
            closing += f"，**{second_label}** 领域紧随其后（**{ranked[1][1]}** 篇）"
        closing += (
            "。整体反映出行业持续向智能化、安全化方向演进，"
            "各领域动态值得持续跟踪。"
        )
        lines.append(closing)

    return "\n\n".join(lines)


def _build_hot_analysis(groups: dict[str, list[dict]], total: int) -> str:
    """Build a hot analysis section analyzing today's news hotspots."""
    if not groups:
        return "今日暂无数据可供热点分析。"

    ranked = sorted(
        [(cat, len(items)) for cat, items in groups.items()],
        key=lambda x: -x[1],
    )

    analysis_parts: list[str] = []

    # Top 3 categories
    analysis_parts.append("**📊 热点分布分析**")
    for i, (cat, count) in enumerate(ranked[:3], 1):
        label = CATEGORY_LABELS.get(cat, cat)
        pct = round(count / total * 100, 1) if total > 0 else 0
        bar = "█" * max(1, int(pct / 5))
        analysis_parts.append(f"  **{i}. {label}** {bar} {count}篇 ({pct}%)")

    # Cross-domain trends
    analysis_parts.append("")
    analysis_parts.append("**🔥 热点趋势判断**")
    trend_lines = []
    for cat, count in ranked[:5]:
        label = CATEGORY_LABELS.get(cat, cat)
        if count >= 5:
            trend_lines.append(f"  - **{label}**：热度 **{label}** 领域资讯集中，建议重点关注头部事件。")
        elif count >= 3:
            trend_lines.append(f"  - **{label}**：关注度中等，有持续更新趋势。")
        else:
            trend_lines.append(f"  - **{label}**：有少量重要动态，属常规更新节奏。")
    analysis_parts.extend(trend_lines)

    # Source diversity
    all_sources: set[str] = set()
    for cat_items in groups.values():
        for item in cat_items:
            s = item.get("source", "")
            if s:
                all_sources.add(s)
    analysis_parts.append("")
    analysis_parts.append(
        f"**📡 信源覆盖**：今日资讯来自 **{len(all_sources)}** 个不同信源，"
        f"信源多样性 **{'丰富' if len(all_sources) >= 10 else '良好' if len(all_sources) >= 5 else '一般'}**。"
    )

    return "\n".join(analysis_parts)


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
        f"今日精选 **{len(articles)}** 篇代表性文章，"
        f"来自 **{sources_str}** 等来源。"
    )
    return f"{base}{detail}" if base else detail


def generate_daily_overview() -> dict[str, Any]:
    """Generate the daily overview for today.

    Returns structured dict with main_theme, hot_analysis, highlights, other_news, stats.
    """
    start_iso, end_iso, date_label = _today_range()
    items = _fetch_today_data(start_iso, end_iso)
    total = len(items)
    groups = _group_by_category(items)

    # Category counts
    category_counts: dict[str, int] = {}
    for cat, cat_items in groups.items():
        lbl = CATEGORY_LABELS.get(cat, cat)
        category_counts[lbl] = len(cat_items)

    main_theme = _build_main_theme(groups, total)
    hot_analysis = _build_hot_analysis(groups, total)
    highlights = _build_highlights(groups)

    # Other news: items not in top 3 of any category (i.e. beyond the 3 per category)
    other_news: list[dict] = []
    for cat, cat_items in groups.items():
        if len(cat_items) > 3:
            for item in cat_items[3:]:
                other_news.append({
                    "id": item["id"],
                    "title": item["title"],
                    "url": item.get("url", ""),
                    "source": item.get("source", ""),
                    "category": item.get("category", ""),
                    "category_label": CATEGORY_LABELS.get(item.get("category", ""), item.get("category", "")),
                })
    other_news = other_news[:50]  # cap at 50

    # Stats
    unique_sources = set()
    for item in items:
        s = item.get("source", "")
        if s:
            unique_sources.add(s)
    reading_time = max(1, round(total * 0.5))

    return {
        "date": date_label,
        "total": total,
        "category_counts": category_counts,
        "main_theme": main_theme,
        "hot_analysis": hot_analysis,
        "highlights": highlights,
        "other_news": other_news,
        "stats": {
            "events": total,
            "selected": total,
            "sources": len(unique_sources),
            "reading_time": reading_time,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


__all__ = [
    "generate_daily_overview",
]
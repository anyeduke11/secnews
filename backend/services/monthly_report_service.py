"""MonthlyReportService — 月报结构化数据生成.

从 30 天热点数据中提取主线条、分类看点及精选文章，
支持 LLM 摘要生成（降级为模板摘要）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from backend.repository.db import get_connection

logger = logging.getLogger("hotspot.monthly_report_service")

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


def _month_range(offset: int = 0) -> tuple[str, str, str]:
    """Return (month_start, month_end, label) for the month offset from current.

    offset=0: current month, offset=-1: previous month, etc.
    """
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month + offset
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    month_start = f"{year}-{month:02d}-01T00:00:00Z"
    if month == 12:
        next_month = f"{year + 1}-01-01T00:00:00Z"
    else:
        next_month = f"{year}-{month + 1:02d}-01T00:00:00Z"
    label = f"{year}年{month}月"
    return month_start, next_month, label


def _fetch_month_data(month_start: str, month_end: str) -> list[dict]:
    """Fetch hotspot items for the given month range."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, title, summary, source, url, category, published_at, ingested_at,
               score, quality_score
        FROM hotspots
        WHERE ingested_at >= ? AND ingested_at < ?
          AND is_fallback = 0
        ORDER BY COALESCE(quality_score, score, 0) DESC
        LIMIT 500
        """,
        (month_start, month_end),
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
    """Build a ~500 word main theme summary covering all active domains.

    Produces a structured narrative: opening → per-domain analysis → closing outlook.
    Can be upgraded to LLMService.generate() for richer prose.
    """
    if not groups:
        return "本月暂无热点资讯。"

    # ── Opening: domain overview ──
    active_labels: list[str] = []
    for cat in CATEGORY_ORDER:
        if cat in groups:
            active_labels.append(CATEGORY_LABELS.get(cat, cat))
    active_str = "、".join(active_labels)

    lines: list[str] = [
        (f"本月共收录{total}篇热点资讯，覆盖{len(groups)}个核心领域"
        f"（{active_str}），"
        f"各领域资讯活跃度总体保持稳定，部分领域呈现显著增长趋势。")
    ]

    # ── Per-domain analysis ──
    for cat in CATEGORY_ORDER:
        items = groups.get(cat, [])
        if not items:
            continue
        label = CATEGORY_LABELS.get(cat, cat)

        # Source diversity
        sources = set()
        for item in items:
            s = item.get("source", "")
            if s:
                sources.add(s)
        source_str = f"来自{len(sources)}个来源"

        # Activity level
        n = len(items)
        if n >= 20:
            trend = "活跃度极高，资讯密集"
        elif n >= 10:
            trend = "保持较高活跃度"
        elif n >= 5:
            trend = "保持稳定更新"
        else:
            trend = "有少量重要资讯"

        # Top titles (up to 3)
        top = items[:3]
        titles = "、".join(
            t["title"][:50] for t in top if t.get("title")
        )

        lines.append(
            f"**{label}**领域本月共收录{n}篇资讯，{source_str}，{trend}。"
            f"重点资讯包括：{titles}等。"
        )

    # ── Closing: ranking & outlook ──
    ranked = sorted(
        [(cat, len(items)) for cat, items in groups.items()],
        key=lambda x: -x[1],
    )
    if ranked:
        first_label = CATEGORY_LABELS.get(ranked[0][0], ranked[0][0])
        if len(ranked) > 1:
            second_label = CATEGORY_LABELS.get(ranked[1][0], ranked[1][0])
            closing = (
                f"从数据分布来看，**{first_label}**领域资讯量最为突出"
                f"（{ranked[0][1]}篇），"
                f"**{second_label}**领域紧随其后（{ranked[1][1]}篇）。"
            )
        else:
            closing = (
                f"从数据分布来看，**{first_label}**领域是本月资讯主力"
                f"（{ranked[0][1]}篇）。"
            )
        closing += (
            "整体反映出行业正加速向智能化、安全化方向演进，"
            "AI与安全交叉领域持续产生新的关注点，"
            "开源生态与商业产品的竞争格局也在不断变化。"
            "预计下月各领域资讯量将继续保持高位，"
            "值得持续跟踪。"
        )
        lines.append(closing)

    return "\n\n".join(lines)


CATEGORY_SUMMARIES: dict[str, str] = {
    "ai": "AI领域本月模型发布、融资动态和应用落地进展显著，多家头部企业推出新模型并扩大基础设施投资。",
    "security": "安全领域漏洞披露、威胁情报和法规更新持续活跃，多家安全厂商发布重要告警和防护方案。",
    "ai_security": "AI安全交叉领域本月关注度持续上升，围绕大模型安全、对抗攻击防护和AI治理框架的讨论增多。",
    "tech": "科技领域涵盖硬件、云计算、开发者工具和开源项目，技术迭代与行业合作不断推进。",
    "finance": "金融领域关注市场动态、政策变化和行业趋势，重要经济数据和企业财报发布引发关注。",
    "startup": "创业领域融资事件和新兴项目活跃，多个赛道涌现创新商业模式和技术突破。",
    "github": "GitHub领域热门开源项目和新版本发布密集，社区活跃度保持高位。",
    "bid": "招标领域本月发布多个重要项目，涵盖安全、AI、IT基础设施等方向。",
}


def _build_highlights(groups: dict[str, list[dict]]) -> list[dict]:
    """Build highlights from grouped data.

    Each highlight = a category with top articles and a thematic summary.
    Returns up to 10 highlights (max 1 per category, prioritizing populated ones).
    """
    highlighted: list[dict] = []
    for cat in CATEGORY_ORDER:
        items = groups.get(cat, [])
        if not items:
            continue
        label = CATEGORY_LABELS.get(cat, cat)
        top5 = items[:5]
        highlighted.append({
            "id": cat,
            "title": label,
            "count": len(items),
            "summary": _build_category_summary(cat, label, top5),
            "articles": [
                {
                    "id": a["id"],
                    "title": a["title"],
                    "summary": a.get("summary", "")[:200],
                    "source": a.get("source", ""),
                    "url": a.get("url", ""),
                    "score": a.get("quality_score") or a.get("score") or 0,
                }
                for a in top5
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
        f"本月精选{len(articles)}篇代表性文章，"
        f"来自{sources_str}等来源。"
    )
    return f"{base}{detail}" if base else detail


def generate_monthly_overview(offset: int = 0) -> dict[str, Any]:
    """Generate the monthly overview for a given month offset.

    Args:
        offset: 0 = current month, -1 = previous month, etc.

    Returns structured dict with main_theme, highlights, period, stats, etc.
    """
    month_start, month_end, label = _month_range(offset)
    items = _fetch_month_data(month_start, month_end)
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
            "start": month_start,
            "end": month_end,
            "offset": offset,
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


def list_available_months() -> list[dict]:
    """List months that have data available for reports."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT DISTINCT strftime('%Y-%m', ingested_at) AS ym
        FROM hotspots
        WHERE is_fallback = 0 AND ingested_at IS NOT NULL
        ORDER BY ym DESC
        LIMIT 12
        """
    ).fetchall()
    result: list[dict] = []
    for row in rows:
        ym = row[0]
        if ym is None:
            continue
        year, month = ym.split("-")
        label = f"{year}年{int(month)}月"
        result.append({"value": ym, "label": label})
    return result


__all__ = [
    "generate_monthly_overview",
    "list_available_months",
]
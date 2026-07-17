"""Phase 1j Task 10.8: Weekly knowledge summary service.

Generates ``knowledge/summaries/weekly-{year_week}.md`` digest files
aggregating the week's new items, new/updated concepts, and learning
progress snapshot.

Design notes:
- Items are filtered by ``ingested_at`` (UTC ISO string with ``Z`` suffix).
- Concepts table has no ``created_at`` column; we fall back to
  ``updated_at`` as an approximation for "active this week".
- Progress table has no timestamp; we snapshot the current totals.
- Output is Markdown with YAML frontmatter (truth-source convention).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from backend.repository.db import get_connection
from backend.repository.knowledge_repo import knowledge_repo
from backend.services.knowledge_sync import KNOWLEDGE_DIR

log = logging.getLogger("hotspot.summary_service")

SUMMARIES_DIR = KNOWLEDGE_DIR / "summaries"

# Domain labels (kept in sync with soul_service.py)
DOMAIN_LABELS: dict[str, str] = {
    "security": "网络安全",
    "ai": "人工智能",
    "startup": "独立开发/创业",
    "finance": "金融/投资",
    "dev": "开发技术",
    "business": "企业管理",
    "general": "综合",
    "other": "其他",
}


def _iso_week_range(year_week: str) -> tuple[date, date]:
    """Parse ``YYYY-Www`` (ISO week) and return (Monday, Sunday) dates."""
    try:
        year_str, week_str = year_week.split("-W", 1)
        year, week = int(year_str), int(week_str)
    except (ValueError, AttributeError):
        raise ValueError(f"invalid year_week format: {year_week!r} (expected YYYY-Www)")
    # ISO week: Monday of week 1 is the date with isocalendar week == 1
    # date.fromisocalendar exists in Python 3.8+
    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _query_items_in_range(start: date, end: date) -> list[dict]:
    """Query items with ingested_at in [start, end+1day)."""
    start_iso = start.strftime("%Y-%m-%d")
    end_iso = (end + timedelta(days=1)).strftime("%Y-%m-%d")
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, title, source, domain, topic, type, difficulty, compiled,
               ingested_at, source_url
        FROM knowledge_items
        WHERE ingested_at >= ? AND ingested_at < ?
        ORDER BY ingested_at DESC
        """,
        (start_iso, end_iso),
    ).fetchall()
    return [dict(r) for r in rows]


def _query_concepts_in_range(start: date, end: date) -> list[dict]:
    """Query concepts with updated_at in [start, end+1day).

    Note: knowledge_concepts table has no created_at column; updated_at
    is used as an approximation for "active this week".
    """
    start_iso = start.strftime("%Y-%m-%d")
    end_iso = (end + timedelta(days=1)).strftime("%Y-%m-%d")
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT slug, title, domain, updated_at
        FROM knowledge_concepts
        WHERE updated_at >= ? AND updated_at < ?
        ORDER BY updated_at DESC
        """,
        (start_iso, end_iso),
    ).fetchall()
    return [dict(r) for r in rows]


def _query_progress_snapshot() -> dict:
    """Snapshot current learning progress totals (no timestamp filter)."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN mastery >= 80 THEN 1 ELSE 0 END) AS mastered,
          SUM(CASE WHEN mastery >= 50 AND mastery < 80 THEN 1 ELSE 0 END) AS learning,
          SUM(CASE WHEN test_count > 0 THEN 1 ELSE 0 END) AS tested
        FROM knowledge_progress
        """,
    ).fetchone()
    if not rows:
        return {"total": 0, "mastered": 0, "learning": 0, "tested": 0}
    return dict(rows)


def _build_markdown(
    year_week: str,
    start: date,
    end: date,
    items: list[dict],
    concepts: list[dict],
    progress: dict,
) -> str:
    """Render the weekly summary Markdown body."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Domain distribution
    domain_counts: dict[str, int] = {}
    for it in items:
        d = it.get("domain") or "uncategorized"
        domain_counts[d] = domain_counts.get(d, 0) + 1
    domain_lines = [
        f"- {DOMAIN_LABELS.get(d, d)}: {c}" for d, c in
        sorted(domain_counts.items(), key=lambda x: -x[1])
    ] or ["- (无)"]

    # Top items (newest 10)
    top_items_lines = []
    for it in items[:10]:
        title = it.get("title") or "(untitled)"
        d = it.get("domain") or "-"
        url = it.get("source_url") or ""
        link = f"[{title}]({url})" if url else title
        top_items_lines.append(f"- [{d}] {link}")

    # Concepts list (top 15)
    concept_lines = []
    for c in concepts[:15]:
        title = c.get("title") or c.get("slug") or "(unnamed)"
        d = c.get("domain") or "-"
        concept_lines.append(f"- [{d}] {title}")

    # Data quality section
    if items:
        compiled_count = sum(1 for it in items if it.get("compiled"))
        compile_rate = compiled_count / len(items) * 100
        quality_lines = [
            f"- 新增条目中已编译：{compiled_count} / {len(items)}",
            f"- 编译率：{compile_rate:.1f}%",
        ]
    else:
        quality_lines = ["- 无新条目"]

    md = f"""---
year_week: "{year_week}"
period: "{start.isoformat()} ~ {end.isoformat()}"
generated_at: "{now_iso}"
items_count: {len(items)}
concepts_count: {len(concepts)}
progress_total: {progress.get('total', 0)}
---

# 周回顾 {year_week}

> 周期：{start.isoformat()} ~ {end.isoformat()}（ISO 周）

## 1. 新增条目 ({len(items)})

### 域分布

{chr(10).join(domain_lines)}

### 最新条目 (Top 10)

{chr(10).join(top_items_lines) or "- (无)"}

## 2. 活跃概念 ({len(concepts)})

> 以 ``updated_at`` 近似（concepts 表无 ``created_at`` 列）

{chr(10).join(concept_lines) or "- (无)"}

## 3. 学习进度快照

- 总概念数：{progress.get('total', 0)}
- 已掌握 (mastery≥80)：{progress.get('mastered', 0)}
- 学习中 (50≤mastery<80)：{progress.get('learning', 0)}
- 已测试：{progress.get('tested', 0)}

## 4. 数据质量

{chr(10).join(quality_lines)}
"""
    return md


def generate_weekly_summary(year_week: Optional[str] = None) -> dict:
    """Generate the weekly summary file for the given ISO week.

    Args:
        year_week: ``YYYY-Www`` format (e.g. ``"2026-W29"``). If None,
            uses the current ISO week.

    Returns:
        Dict with ``path``, ``year_week``, ``items_count``, ``concepts_count``.
    """
    if year_week is None:
        today = date.today()
        iso = today.isocalendar()
        year_week = f"{iso.year}-W{iso.week:02d}"

    start, end = _iso_week_range(year_week)
    log.info("generating weekly summary for %s (%s ~ %s)", year_week, start, end)

    items = _query_items_in_range(start, end)
    concepts = _query_concepts_in_range(start, end)
    progress = _query_progress_snapshot()

    md = _build_markdown(year_week, start, end, items, concepts, progress)

    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SUMMARIES_DIR / f"weekly-{year_week}.md"
    out_path.write_text(md, encoding="utf-8")
    log.info("weekly summary written: %s (items=%d concepts=%d)",
             out_path, len(items), len(concepts))

    return {
        "path": str(out_path),
        "year_week": year_week,
        "items_count": len(items),
        "concepts_count": len(concepts),
        "progress_total": progress.get("total", 0),
    }


def list_summaries() -> list[dict]:
    """List all weekly summary files sorted by year_week DESC."""
    if not SUMMARIES_DIR.exists():
        return []
    out = []
    for md in SUMMARIES_DIR.glob("weekly-*.md"):
        # filename: weekly-2026-W29.md
        stem = md.stem  # weekly-2026-W29
        yw = stem.replace("weekly-", "", 1)
        out.append({
            "year_week": yw,
            "filename": md.name,
            "path": str(md),
            "size": md.stat().st_size,
            "mtime": int(md.stat().st_mtime),
        })
    out.sort(key=lambda x: x["year_week"], reverse=True)
    return out


__all__ = ["generate_weekly_summary", "list_summaries"]

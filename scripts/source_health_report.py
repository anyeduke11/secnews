"""Phase 48: source_health 监控脚本

输出每个 source 的健康状态:
- source_name
- category
- status (active/stale/dead)
- 本周 active 条数
- 累计 total_items
- zero_yield_runs (连续零产出)
- last_seen (最近一次产出 >=1 item)
- last_error
- 错配 category_mismatch 数量 (本周)

用法:
    /path/to/hotspot/.venv/bin python scripts/source_health_report.py
    /path/to/hotspot/.venv/bin python scripts/source_health_report.py --category bid
    /path/to/hotspot/.venv/bin python scripts/source_health_report.py --status dead --top 20
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "hotspot.db"

# 本周一 00:00 UTC
def week_start_iso() -> str:
    now = datetime.now(timezone.utc)
    monday = now.date() - __import__("datetime").timedelta(days=now.weekday())
    return f"{monday}T00:00:00+00:00"


def fmt_row(row: tuple) -> str:
    cat, name, status, runs, zero_y, items, last_seen, err, week_active, week_mismatch = row
    last_seen_short = (last_seen or "")[:10]
    err_short = (err or "")[:30]
    return (
        f"{cat:9s} {name:18s} {status:6s} "
        f"runs={runs:3d} zero={zero_y:3d} items={items:5d} "
        f"wk={week_active:2d} mis={week_mismatch:2d} "
        f"seen={last_seen_short:10s} err={err_short}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", help="filter by category (security/ai/finance/startup/bid/tech/github)")
    ap.add_argument("--status", choices=["active", "stale", "dead"])
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    ws = week_start_iso()

    query = """
    SELECT
      ss.category,
      ss.source_name,
      ss.status,
      ss.total_runs,
      ss.zero_yield_runs,
      ss.total_items,
      ss.last_seen_at,
      ss.last_error,
      COALESCE((
        SELECT COUNT(*) FROM hotspots h
        WHERE h.source = ss.source_name
          AND h.category = ss.category
          AND h.is_fallback = 0
          AND h.published_at >= ?
      ), 0) AS week_active,
      COALESCE((
        SELECT COUNT(*) FROM hotspots h
        WHERE h.source = ss.source_name
          AND h.category = ss.category
          AND h.is_fallback = 0
          AND h.published_at >= ?
          AND h.quality_flags LIKE '%category_mismatch%'
      ), 0) AS week_mismatch
    FROM source_stats ss
    WHERE 1=1
    """
    params: list = [ws, ws]
    if args.category:
        query += " AND ss.category = ?"
        params.append(args.category)
    if args.status:
        query += " AND ss.status = ?"
        params.append(args.status)
    query += """
    ORDER BY
      CASE ss.status WHEN 'active' THEN 0 WHEN 'stale' THEN 1 ELSE 2 END,
      ss.total_items DESC
    LIMIT ?
    """
    params.append(args.top)

    rows = conn.execute(query, params).fetchall()
    if not rows:
        print("(no rows)")
        return 0

    print(f"=== source_health report (week_start={ws[:10]}) ===")
    for r in rows:
        print(fmt_row(r))

    # Summary
    n_active = sum(1 for r in rows if r[2] == "active")
    n_stale = sum(1 for r in rows if r[2] == "stale")
    n_dead = sum(1 for r in rows if r[2] == "dead")
    total_active_week = sum(r[8] for r in rows)
    total_mismatch_week = sum(r[9] for r in rows)
    print()
    print(
        f"--- summary: total={len(rows)} "
        f"active={n_active} stale={n_stale} dead={n_dead} "
        f"| week_active={total_active_week} week_mismatch={total_mismatch_week}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

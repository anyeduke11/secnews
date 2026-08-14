"""Crawler v2 Phase 0.5 — 把现有 collector 硬编码源注册进 crawler_sources 表。

Strangler 迁移的「并行运行期」第一步: 旁路写入, 不改变现有采集逻辑。
crawler_sources 表 (migration 055) 已建但为空; 本脚本把 7 个 collector
的 ``{CATEGORY}_SOURCES`` 常量提取并幂等注册 (INSERT OR IGNORE), 使源
注册表开始积累基线数据, 供后续切流 (Phase 1+) 使用。

用法:
    python -m backend.scripts.seed_crawler_sources            # 实际写入
    python -m backend.scripts.seed_crawler_sources --dry-run  # 只预览

注意: 只读现有 SOURCES 常量, 不 import collector 类 (避免触发采集逻辑)。
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

# category → (collector 模块, SOURCES 常量名)
_SOURCE_MODULES: list[tuple[str, str, str]] = [
    ("ai", "backend.collectors.ai_collector", "AI_SOURCES"),
    ("security", "backend.collectors.security_collector", "SECURITY_SOURCES"),
    ("finance", "backend.collectors.finance_collector", "FINANCE_SOURCES"),
    ("startup", "backend.collectors.startup_collector", "STARTUP_SOURCES"),
    ("tech", "backend.collectors.tech_collector", "TECH_SOURCES"),
    ("github", "backend.collectors.github_collector", "GITHUB_SOURCES"),
    ("bid", "backend.collectors.bid_collector", "BID_SOURCES"),
]

_CATEGORY_LABEL = {
    "ai": "ai", "security": "security", "finance": "finance",
    "startup": "startup", "tech": "tech", "github": "github", "bid": "bid",
}


def _collect_sources() -> list[dict]:
    """从各 collector 模块提取源条目 (只读常量, 不触发采集)."""
    collected: list[dict] = []
    for category, mod_name, const in _SOURCE_MODULES:
        try:
            mod = __import__(mod_name, fromlist=[const])
        except ImportError as e:
            print(f"WARN: skip {mod_name}: {e}", file=sys.stderr)
            continue
        entries = getattr(mod, const, []) or []
        for s in entries:
            if not s.get("name"):
                continue
            collected.append({
                "category": category,
                "name": s["name"],
                "url": s.get("url") or "",
                "feed_url": s.get("rss_url") or "",
                "kind": "rss" if s.get("rss_url") else "html",
                "priority": int(s.get("score") or 50),
                "renderer": s.get("renderer") or "",
            })
    return collected


def seed_crawler_sources(dry_run: bool = False) -> dict:
    """注册源到 crawler_sources 表 (幂等, INSERT OR IGNORE).

    Returns:
        {"total": n, "inserted": m, "skipped": k, "by_category": {...}}
    """
    from backend.repository.db import get_connection

    sources = _collect_sources()
    conn = get_connection()
    inserted = 0
    skipped = 0
    by_cat: dict[str, int] = {}

    for s in sources:
        if dry_run:
            by_cat[s["category"]] = by_cat.get(s["category"], 0) + 1
            continue
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO crawler_sources
                    (id, category, name, kind, url, feed_url,
                     cadence_seconds, priority, max_items, enabled,
                     use_proxy, created_at, updated_at, status)
                VALUES
                    (?, ?, ?, ?, ?, ?,
                     300, ?, 50, 1,
                     'auto', datetime('now'), datetime('now'), 'unknown')
                """,
                (
                    f"{s['category']}:{s['name']}",
                    s["category"], s["name"], s["kind"],
                    s["url"], s["feed_url"],
                    s["priority"],
                ),
            )
            if cur.rowcount:
                inserted += 1
                by_cat[s["category"]] = by_cat.get(s["category"], 0) + 1
            else:
                skipped += 1
        except Exception as e:
            print(f"WARN: insert {s['name']} failed: {e}", file=sys.stderr)

    result = {
        "total": len(sources),
        "inserted": 0 if dry_run else inserted,
        "skipped": skipped,
        "by_category": by_cat,
        "dry_run": dry_run,
    }
    print(
        f"[crawler-sources] total={result['total']} "
        f"inserted={result['inserted']} skipped={result['skipped']} "
        f"dry_run={dry_run}"
    )
    for cat, n in sorted(by_cat.items()):
        print(f"  {cat}: {n}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed crawler_sources from collectors")
    parser.add_argument("--dry-run", action="store_true", help="preview only")
    args = parser.parse_args()
    seed_crawler_sources(dry_run=args.dry_run)

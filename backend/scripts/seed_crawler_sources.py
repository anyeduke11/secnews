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

# category → (collector 模块, 实例化类)
# P1 修正: 用 collector **实例** 的 ``sources`` (实际生效源) 而非 SOURCES
# 常量 — 常量可能含子类过滤掉的源 (如 SecurityCollector 的 SOURCE_BLACKLIST
# 过滤 KrebsOnSecurity/启明星辰), 用常量注册会导致切流后重新抓取黑名单源。
_COLLECTOR_CLASSES: list[tuple[str, str, str]] = [
    ("ai", "backend.collectors.ai_collector", "AICollector"),
    ("security", "backend.collectors.security_collector", "SecurityCollector"),
    ("finance", "backend.collectors.finance_collector", "FinanceCollector"),
    ("startup", "backend.collectors.startup_collector", "StartupCollector"),
    ("tech", "backend.collectors.tech_collector", "TechCollector"),
    ("github", "backend.collectors.github_collector", "GitHubCollector"),
    ("bid", "backend.collectors.bid_collector", "BidCollector"),
]


def _collect_sources() -> list[dict]:
    """从各 collector 实例提取**实际生效**源 (只读, 不触发采集).

    实例化 collector 只读取类配置 (sources/renderer/keywords), 不执行
    collect() 抓取 — 安全且与切流后的采集行为完全一致 (含黑名单过滤)。
    """
    collected: list[dict] = []
    for category, mod_name, cls_name in _COLLECTOR_CLASSES:
        try:
            mod = __import__(mod_name, fromlist=[cls_name])
            collector = getattr(mod, cls_name)()
        except (ImportError, AttributeError) as e:
            print(f"WARN: skip {mod_name}: {e}", file=sys.stderr)
            continue
        # 同名多条目去重: 优先 enabled=1 的 (如 华尔街见闻/雪球 有
        # renderer=disabled 直抓禁用 + renderer=wechat 公众号替代两个条目,
        # crawler_sources 以 name 为主键只能注册一条 — 取实际抓取的替代条目)。
        by_name: dict[str, dict] = {}
        for s in collector.sources or []:
            if not s.get("name"):
                continue
            renderer = s.get("renderer") or ""
            enabled = 0 if renderer == "disabled" else 1
            entry = {
                "category": category,
                "name": s["name"],
                "url": s.get("url") or "",
                "feed_url": s.get("rss_url") or "",
                "kind": "rss" if s.get("rss_url") else "html",
                "priority": int(s.get("score") or 50),
                "renderer": renderer,
                "enabled": enabled,
            }
            prev = by_name.get(s["name"])
            if prev is None or (enabled and not prev["enabled"]):
                by_name[s["name"]] = entry
        collected.extend(by_name.values())
    return collected


def seed_crawler_sources(dry_run: bool = False, reset: bool = False) -> dict:
    """注册源到 crawler_sources 表 (幂等, INSERT OR IGNORE).

    Args:
        dry_run: 只预览不写入。
        reset: 先清空 crawler_sources 再全量重灌 (用于修正历史 seed 数据,
            如 renderer=disabled 源此前被 enabled=1 注册)。

    Returns:
        {"total": n, "inserted": m, "skipped": k, "by_category": {...}}
    """
    from backend.repository.db import get_connection

    sources = _collect_sources()
    conn = get_connection()
    inserted = 0
    skipped = 0
    by_cat: dict[str, int] = {}

    if reset and not dry_run:
        conn.execute("DELETE FROM crawler_sources")
        print("[crawler-sources] reset: crawler_sources cleared", file=sys.stderr)

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
                     300, ?, 50, ?,
                     'auto', datetime('now'), datetime('now'), 'unknown')
                """,
                (
                    f"{s['category']}:{s['name']}",
                    s["category"], s["name"], s["kind"],
                    s["url"], s["feed_url"],
                    s["priority"],
                    s["enabled"],
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
    parser.add_argument("--reset", action="store_true", help="clear table before seeding")
    args = parser.parse_args()
    seed_crawler_sources(dry_run=args.dry_run, reset=args.reset)

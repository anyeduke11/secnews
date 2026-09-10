"""audit_network_paths — 信源抓取网络路径清单 (国际/国内归属 × 渲染器 × 代理策略, 只读).

用法::

    .venv/bin/python scripts/audit_network_paths.py            # 全部启用源
    .venv/bin/python scripts/audit_network_paths.py --zone international
    .venv/bin/python scripts/audit_network_paths.py --md reports/network_paths.md

对 owner 的问题 "哪些是国外站点、抓取网络路径是什么" 给出权威清单:
    - zone: crawler_sources.network_zone (migration 110, 人工核定的国际/国内归属)
    - path: 该源实际走的抓取路径, 按渲染器与 zone 推导:
        international + renderer=aiohttp/rss → 代理优先 → (代理失败) 直连
        international + renderer=crawl4ai    → 代理优先 → (失败) 直连 → crawl4ai (无代理)
        domestic  + 任意渲染器               → 直连 (永不走代理), 失败仅 crawl4ai/代理清单外兜底
    - 未注册分类的采集器 (HN/GDELT/OpenBB/OSSInsight/Telegram/Reddit) 单列:
        走 BackendSession / 自建 session, 国外 API 源经 should_use_proxy 已代理优先。

只读契约 (scripts/AGENTS.md audit_*): 主库 mode=ro, 全程 SELECT。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.config import config  # noqa: E402

# 未进 crawler_sources 注册表的采集器 (CollectionService 内建, 各自固定路径)
_COLLECTOR_LEVEL_PATHS = [
    ("HackerNews (ai)", "HNCollector", "BackendSession → hn API (国外, 代理优先→直连回退)"),
    ("GDELT (security)", "GDELTCollector", "BackendSession → GDELT API (国外, 代理优先→直连回退)"),
    ("OpenBB (finance)", "OpenBBCollector", "自建 session → OpenBB API (国外, 直连优先)"),
    ("OSSInsight (tech)", "OSSInsightCollector", "自建 session → GitHub API (国外, 直连优先)"),
    ("Telegram (tech)", "TelegramCollector", "自建 session → t.me (国外, 直连优先)"),
    ("Reddit (tech)", "RedditCollector", "Crawl4aiParser → Reddit (国外, 渲染不走代理)"),
]


_COLLECTOR_BY_CATEGORY = {
    "ai": ("backend.collectors.ai_collector", "AICollector"),
    "ai_security": ("backend.collectors.ai_security_collector", "AISecurityCollector"),
    "security": ("backend.collectors.security_collector", "SecurityCollector"),
    "finance": ("backend.collectors.finance_collector", "FinanceCollector"),
    "startup": ("backend.collectors.startup_collector", "StartupCollector"),
    "bid": ("backend.collectors.bid_collector", "BidCollector"),
    "github": ("backend.collectors.github_collector", "GitHubCollector"),
    "tech": ("backend.collectors.tech_collector", "TechCollector"),
}
_collector_cache: dict[str, object] = {}


def _collector_for(category: str):
    if category not in _collector_cache:
        import importlib

        mod_name, cls_name = _COLLECTOR_BY_CATEGORY[category]
        _collector_cache[category] = getattr(importlib.import_module(mod_name), cls_name)()
    return _collector_cache[category]


def _renderer_for(row: dict) -> str:
    """镜像 BaseCollector._load_sources_from_registry 的 renderer 解析。"""
    if row["category"] not in _COLLECTOR_BY_CATEGORY:
        return "aiohttp"
    collector = _collector_for(row["category"])
    const = next(
        (s for s in getattr(collector, "sources", []) if s.get("name") == row["name"] and s.get("renderer") != "disabled"),
        None,
    )
    return (const or {}).get("renderer") or collector._get_renderer_by_name().get(row["name"]) or "aiohttp"


def _open_ro() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def derive_path(zone: str, renderer: str) -> str:
    if zone == "international":
        if renderer == "crawl4ai":
            return "代理优先 → 直连回退 → crawl4ai 渲染 (不走代理)"
        return "代理优先 → 直连回退 (ProxySession)"
    if renderer == "crawl4ai":
        return "直连 → crawl4ai 渲染"
    return "直连 (永不走代理)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zone", choices=["international", "domestic"], default=None)
    ap.add_argument("--md", default=None, help="同时落 Markdown 路径 (默认 reports/network_paths.md)")
    args = ap.parse_args()

    conn = _open_ro()
    rows = conn.execute(
        "SELECT id, category, name, url, feed_url, api_url, cadence_seconds, enabled, network_zone FROM crawler_sources WHERE enabled = 1 ORDER BY network_zone DESC, category, name"  # noqa: E501
    ).fetchall()
    conn.close()

    out = []
    for r in rows:
        zone = r["network_zone"] or "domestic"
        if args.zone and zone != args.zone:
            continue
        renderer = _renderer_for(dict(r))
        host = (r["url"] or r["feed_url"] or "").split("//")[-1].split("/")[0]
        out.append({
            "id": r["id"], "category": r["category"], "name": r["name"], "host": host,
            "zone": zone, "renderer": renderer, "cadence": r["cadence_seconds"],
            "path": derive_path(zone, renderer),
        })

    intl = [r for r in out if r["zone"] == "international"]
    print(f"[paths] enabled={len(out)}  international={len(intl)}  domestic={len(out) - len(intl)}\n")
    print(f"{'id':38s} {'zone':14s} {'rend':9s} {'cadence':7s} path")
    for r in out:
        print(f"{r['id'][:38]:38s} {r['zone']:14s} {r['renderer'][:9]:9s} {r['cadence']!s:7s} {r['path']}")

    print("\n[paths] 采集器级 (未进注册表):")
    for name, cls, path in _COLLECTOR_LEVEL_PATHS:
        print(f"  {name:20s} {cls:22s} {path}")

    if args.md:
        md_path = Path(args.md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# 信源抓取网络路径清单 ({datetime.now(timezone.utc).isoformat(timespec='seconds')})", "",
            f"- 启用源 {len(out)}: 国际 {len(intl)} / 国内 {len(out) - len(intl)}; 归属 = crawler_sources.network_zone (migration 110)",
            "- 策略: 国内源永远直连; 国际源代理优先 (ProxySession, 代理失败自动切直连; 熔断期全直连); crawl4ai 渲染不走代理", "",
            "| id | zone | renderer | cadence | 抓取路径 |", "|---|---|---|---|---|",
        ]
        for r in out:
            lines.append(f"| {r['id']} | {r['zone']} | {r['renderer']} | {r['cadence']}s | {r['path']} |")
        lines += ["", "## 采集器级 (未进注册表)", "", "| 源 | collector | 路径 |", "|---|---|---|"]
        for name, cls, path in _COLLECTOR_LEVEL_PATHS:
            lines.append(f"| {name} | {cls} | {path} |")
        lines.append("")
        md_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n[paths] wrote {md_path}")
    (Path(REPO_ROOT / "reports") / "network_paths.json").write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": out}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

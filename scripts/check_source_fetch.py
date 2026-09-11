"""check_source_fetch — 用生产抓取链 (collector.fetch_source) 实测指定源, 不写 DB.

用法::

    .venv/bin/python scripts/check_source_fetch.py bid:招标采购导航网 security:嘶吼
    .venv/bin/python scripts/check_source_fetch.py --offline            # 全部 dead+grace 启用源
    .venv/bin/python scripts/check_source_fetch.py --category bid --limit 10
    .venv/bin/python scripts/check_source_fetch.py --offline --json reports/check_source_fetch.json

与 audit_dead_source_triage 的分工: triage 用独立 urllib 四层探测 "站点可达性";
本脚本走 **生产同款路径** (renderer 路由 → crawl4ai/aiohttp/RSS → _parse_html →
_build_items), 回答 "我们的采集器现在能不能从它拿到条目"。两者对照即可定位
是站死了 (retire) 还是我们的链坏了 (fix)。

只读契约 (scripts/AGENTS.md check_* 规则): crawler_sources 以 mode=ro 读;
fetch_source 本身无 DB 副作用 (log_event 纯日志; 质量门禁/入库在 collect() 层,
本脚本不调 collect)。出网走 collector 自身的 SSRF 门。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.config import config  # noqa: E402

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
        mod_name, cls_name = _COLLECTOR_BY_CATEGORY[category]
        import importlib

        cls = getattr(importlib.import_module(mod_name), cls_name)
        _collector_cache[category] = cls()
    return _collector_cache[category]


def _open_ro() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def load_rows(conn, ids: list[str], offline: bool, category: str | None, limit: int) -> list[dict]:
    rows: list[dict] = []
    if ids:
        for sid in ids:
            r = conn.execute(
                "SELECT id, category, name, kind, url, feed_url, api_url, priority, status, enabled FROM crawler_sources WHERE id = ? OR (category || ':' || name) = ?",  # noqa: E501
                (sid, sid),
            ).fetchone()
            if r is None:
                print(f"[check] not found: {sid}", file=sys.stderr)
            else:
                rows.append(dict(r))
    else:
        sql = "SELECT id, category, name, kind, url, feed_url, api_url, priority, status, enabled FROM crawler_sources WHERE enabled = 1"  # noqa: E501
        params: list = []
        if offline:
            sql += " AND status IN ('dead', 'grace')"
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY category, priority DESC, name"
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    if limit:
        rows = rows[:limit]
    return rows


def build_source_dict(collector, row: dict) -> dict:
    """镜像 BaseCollector._load_sources_from_registry 的字段映射 (含 renderer 解析)."""
    name = row["name"]
    const = next(
        (s for s in getattr(collector, "sources", []) if s.get("name") == name and s.get("renderer") != "disabled"),
        None,
    )
    renderer_by_name = collector._get_renderer_by_name()
    renderer = (const or {}).get("renderer") or renderer_by_name.get(name) or "aiohttp"
    return {
        "name": name,
        "url": row["url"] or "",
        "rss_url": row["feed_url"] or "",
        "api_url": row["api_url"] or "",
        "score": row["priority"],
        "renderer": renderer,
        "keywords": (const or {}).get("keywords", []),
    }


async def check_one(row: dict, timeout: float, sem: asyncio.Semaphore) -> dict:
    out = {"id": row["id"], "category": row["category"], "status": row["status"], "kind": row["kind"]}
    if row["category"] not in _COLLECTOR_BY_CATEGORY:
        out.update(result="skip", error=f"no collector mapping for {row['category']}")
        return out
    async with sem:
        t0 = time.time()
        try:
            collector = _collector_for(row["category"])
            collector.timeout = int(timeout)
            src = build_source_dict(collector, row)
            out["renderer"] = src["renderer"]
            items, sr = await asyncio.wait_for(collector.fetch_source(src), timeout=timeout * 3 + 15)
            raw = getattr(sr, "fetched_count", sr.item_count)
            # ok = 有用条目; alive = 可达可解析但本轮无业务相关条目 (存活口径); zero = 真 0 候选
            result = "ok" if sr.item_count > 0 else ("alive" if raw > 0 else "zero")
            out.update(
                result=result,
                item_count=sr.item_count,
                raw_count=raw,
                error=sr.error_msg,
                duration_ms=sr.duration_ms,
                sample=[getattr(i, "title", str(i))[:60] for i in items[:2]],
            )
        except asyncio.TimeoutError:
            out.update(result="hang", error=f"fetch_source exceeded {timeout * 3 + 15:.0f}s", duration_ms=int((time.time() - t0) * 1000))
        except Exception as e:
            out.update(result="crash", error=f"{type(e).__name__}: {str(e)[:160]}", duration_ms=int((time.time() - t0) * 1000))
    return out


async def run(rows: list[dict], timeout: float, concurrency: int) -> list[dict]:
    sem = asyncio.Semaphore(max(1, concurrency))
    results = await asyncio.gather(*(check_one(r, timeout, sem) for r in rows))
    return list(results)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="源 id (如 bid:招标采购导航网); 留空配合 --offline/--category")
    ap.add_argument("--offline", action="store_true", help="全部 enabled 且 status∈{dead,grace} 的源")
    ap.add_argument("--category", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=float, default=30.0, help="collector.timeout (秒)")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--json", dest="json_out", default=None, help="结果落 JSON 路径")
    args = ap.parse_args()
    if not args.ids and not args.offline and not args.category:
        ap.error("给源 id, 或 --offline / --category")

    conn = _open_ro()
    rows = load_rows(conn, args.ids, args.offline, args.category, args.limit)
    conn.close()
    print(f"[check] {len(rows)} sources, timeout={args.timeout}s concurrency={args.concurrency}")
    t0 = time.time()
    results = asyncio.run(run(rows, args.timeout, args.concurrency))
    print(f"[check] done in {time.time() - t0:.0f}s\n")

    from collections import Counter

    print(f"{'id':36s} {'st':6s} {'rend':9s} {'res':5s} {'raw':>4s} {'n':>4s} {'ms':>6s}  error/sample")
    for r in sorted(results, key=lambda x: (x.get("result", ""), x["category"], x["id"])):
        tail = r.get("error") or " | ".join(r.get("sample") or [])
        print(f"{r['id'][:36]:36s} {r['status'][:6]:6s} {str(r.get('renderer'))[:9]:9s} {r.get('result',''):5s} {r.get('raw_count', '-')!s:>4s} {r.get('item_count', '-')!s:>4s} {r.get('duration_ms', '-')!s:>6s}  {str(tail)[:90]}")
    print("\n[check] result:", dict(Counter(r.get("result") for r in results)))
    if args.json_out:
        p = Path(args.json_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"[check] wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""audit_source_value — 源"有用性"度量: 7 天 per-source 抓取 / 接受 / 入库排行 (只读).

用法::

    .venv/bin/python scripts/audit_source_value.py                # 默认 7 天
    .venv/bin/python scripts/audit_source_value.py --days 14 --top 30

对齐 owner 目标 "不是能抓到多少, 而是多少是有用的": 存活 (fetched_count = 过滤前候选数)
与有用 (accepted_count = 相关性+质量过滤后条目数) 分列, 再对照 hotspots 实际入库数。
cadence 修正批之前 crawler_runs 两列同值, 历史行的 fetched≈accepted 属预期; 修正后新行
才真正分离, 本报告随时间累积价值。

产出 (reports/, gitignored): source_value.json + source_value.md
    - 有用性排行: accepted 总数 desc (前 N)
    - 低价值名单: runs ≥ 阈值 且 accepted = 0 (可达但从未产出相关条目 → 裁源/调 info_filter 依据)
    - 分类汇总: category 维度 fetched / accepted / 接受率

只读契约 (scripts/AGENTS.md audit_*): 主库 + warm 库 mode=ro, 全程 SELECT。
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


def _open_ro() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    warm = Path(config.warm_db_path)
    if warm.exists():
        conn.execute("ATTACH DATABASE ? AS warm", (f"file:{warm}?mode=ro",))
    return conn


def _runs_table(conn: sqlite3.Connection) -> str | None:
    for cand in ("warm.crawler_runs", "main.crawler_runs"):
        schema, name = cand.split(".")
        try:
            row = conn.execute(
                f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?", (name,)  # noqa: S608 - schema 名来自固定白名单
            ).fetchone()
        except sqlite3.Error:
            row = None
        if row:
            return cand
    return None


def collect(conn: sqlite3.Connection, days: int) -> list[dict]:
    """per-source 聚合。crawler_runs.source_id 两种口径 (name / {category}:{slug}) 都归到源 name。"""
    sources = {
        r["id"]: dict(r)
        for r in conn.execute(
            "SELECT id, category, name, kind, enabled, status, cadence_seconds FROM crawler_sources"
        ).fetchall()
    }
    by_name: dict[tuple[str, str], dict] = {}
    for s in sources.values():
        by_name[(s["category"], s["name"])] = {
            **s, "runs": 0, "fetched": 0, "accepted": 0, "failed_runs": 0,
            "last_success_at": None, "hotspots_ingested": 0,
        }
    runs_table = _runs_table(conn)
    if runs_table:
        # noqa: 表名来自固定白名单 (_runs_table), 无用户输入
        rows = conn.execute(
            f"SELECT source_id, category, COUNT(*) AS runs, COALESCE(SUM(fetched_count),0) AS fetched, COALESCE(SUM(accepted_count),0) AS accepted, COALESCE(SUM(status='failed'),0) AS failed_runs, MAX(CASE WHEN accepted_count > 0 THEN started_at END) AS last_success_at FROM {runs_table} WHERE started_at >= datetime('now', ?) GROUP BY source_id, category",  # noqa: E501,S608
            (f"-{int(days)} days",),
        ).fetchall()
        for r in rows:
            sid, cat = r["source_id"], r["category"]
            key = (cat, sources[sid]["name"]) if sid in sources else (cat, sid)
            agg = by_name.setdefault(key, {
                "id": sid, "category": cat, "name": key[1], "kind": "?", "enabled": None, "status": "?",
                "cadence_seconds": None, "runs": 0, "fetched": 0, "accepted": 0, "failed_runs": 0,
                "last_success_at": None, "hotspots_ingested": 0,
            })
            agg["runs"] += r["runs"]
            agg["fetched"] += r["fetched"]
            agg["accepted"] += r["accepted"]
            agg["failed_runs"] += r["failed_runs"]
            if r["last_success_at"] and (agg["last_success_at"] is None or r["last_success_at"] > agg["last_success_at"]):
                agg["last_success_at"] = r["last_success_at"]
    # 实际入库 (hotspots.source = name)
    try:
        for r in conn.execute(
            "SELECT category, source, COUNT(*) AS n FROM hotspots WHERE ingested_at >= datetime('now', ?) GROUP BY category, source",
            (f"-{int(days)} days",),
        ).fetchall():
            key = (r["category"], r["source"])
            if key in by_name:
                by_name[key]["hotspots_ingested"] = r["n"]
    except sqlite3.Error:
        pass
    out = []
    for v in by_name.values():
        v["acceptance_rate"] = round(v["accepted"] / v["fetched"], 3) if v["fetched"] else None
        v["failure_rate"] = round(v["failed_runs"] / v["runs"], 3) if v["runs"] else None
        out.append(v)
    return out


def render_md(rows: list[dict], days: int, top: int, low_runs: int) -> str:
    def fmt(v):
        return "-" if v is None else v
    ranked = sorted([r for r in rows if r["accepted"] > 0], key=lambda r: (-r["accepted"], -r["hotspots_ingested"]))
    low = sorted([r for r in rows if r["runs"] >= low_runs and r["accepted"] == 0 and r["enabled"] == 1],
                 key=lambda r: -r["runs"])
    cats: dict[str, dict] = {}
    for r in rows:
        c = cats.setdefault(r["category"], {"sources": 0, "enabled": 0, "runs": 0, "fetched": 0, "accepted": 0, "ingested": 0})
        c["sources"] += 1
        c["enabled"] += 1 if r["enabled"] == 1 else 0
        c["runs"] += r["runs"]
        c["fetched"] += r["fetched"]
        c["accepted"] += r["accepted"]
        c["ingested"] += r["hotspots_ingested"]
    lines = [
        f"# 源有用性度量 (audit_source_value, 最近 {days} 天)", "",
        f"- 生成: {datetime.now(timezone.utc).isoformat(timespec='seconds')} | 口径: fetched=过滤前候选(存活) / accepted=过滤后条目(有用) / ingested=hotspots 实际入库",
        "- 注: cadence 修正批之前的历史 run 两列同值 (fetched≈accepted 属预期), 修正后新行才真正分离", "",
        "## 分类汇总", "",
        "| category | 源数 | enabled | runs | fetched | accepted | 接受率 | ingested |", "|---|---|---|---|---|---|---|---|",
    ]
    for cat, c in sorted(cats.items()):
        rate = f"{c['accepted'] / c['fetched']:.1%}" if c["fetched"] else "-"
        lines.append(f"| {cat} | {c['sources']} | {c['enabled']} | {c['runs']} | {c['fetched']} | {c['accepted']} | {rate} | {c['ingested']} |")
    lines += ["", f"## 有用性排行 (accepted desc, top {top})", "",
              "| # | source | category | status | runs | fetched | accepted | 接受率 | ingested | last_success |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(ranked[:top], 1):
        lines.append(f"| {i} | {r['name']} | {r['category']} | {fmt(r['status'])} | {r['runs']} | {r['fetched']} | {r['accepted']} | {fmt(r['acceptance_rate'])} | {r['hotspots_ingested']} | {fmt(r['last_success_at'])[:16] if r['last_success_at'] else '-'} |")
    lines += ["", f"## 低价值名单 (enabled 且 runs ≥ {low_runs} 且 accepted = 0) — 裁源 / 调 info_filter 依据", "",
              "| source | category | status | cadence | runs | fetched | failed_runs |", "|---|---|---|---|---|---|---|"]
    for r in low:
        lines.append(f"| {r['name']} | {r['category']} | {fmt(r['status'])} | {fmt(r['cadence_seconds'])} | {r['runs']} | {r['fetched']} | {r['failed_runs']} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--low-runs", type=int, default=20, help="低价值名单的最小 run 数")
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "reports"))
    args = ap.parse_args()
    conn = _open_ro()
    rows = collect(conn, args.days)
    conn.close()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "source_value.json").write_text(json.dumps({"days": args.days, "rows": rows}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md = render_md(rows, args.days, args.top, args.low_runs)
    (out_dir / "source_value.md").write_text(md, encoding="utf-8")
    print(md.split("## 有用性排行")[0])
    ranked = [r for r in rows if r["accepted"] > 0]
    low = [r for r in rows if r["runs"] >= args.low_runs and r["accepted"] == 0 and r["enabled"] == 1]
    print(f"[value] sources={len(rows)} with_accepted={len(ranked)} low_value(enabled)={len(low)} → {out_dir / 'source_value.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

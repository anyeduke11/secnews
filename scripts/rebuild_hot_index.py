"""rebuild_hot_index — v0.8.8 R-17 管道 B：从冷层 ``feed/*.md`` 重建 ``hotspots`` 热索引。

背景（``docs/audit/DATA_ARCHITECTURE_HOT_COLD_2026-11-11.md`` §4.2）
--------------------------------------------------------------
冷层真源 = ``llm-wiki-2.0/feed/{yyyy-mm}.md``，每行一条 ``<!--hsc:{json}-->``
全列记录（由 ``wiki_archiver.sink_hotspots_to_feed`` 写入）。本脚本是唯一
cold → hot 重建通道，也是取消备份链（C2.1）的合法性前提（RA-14）。

重建口径
--------
1. 解析冷层记录（与 C2.3a 写入端共用同一解析契约）
2. UPSERT ``hotspots`` 20 列（核心业务列由触发器自动同步 FTS，不手写 FTS DML）
3. ``hotspot_tags`` 只回填 ``tags`` 表已存在的 ``tag_id`` — 冷层未持久化
   ``tags.type``，凭空补建 tags 行会伪造概念图；缺失引用计入对账差异
4. 对账：冷层条数 vs DB 行数 / FTS 命中数 → 差异写 ``wiki_events(kind='rebuild_diff')``

用法
----
    python scripts/rebuild_hot_index.py --dry-run            # 预览（默认动作 from-cold）
    python scripts/rebuild_hot_index.py --from-cold          # 恢复场景：冷层记录覆盖同 id 热层行
    python scripts/rebuild_hot_index.py --sync               # 常态增量：跳过已存在 id（INSERT OR IGNORE）
    python scripts/rebuild_hot_index.py --db /tmp/copy.db --wiki-root /tmp/wiki --json

需要已初始化 schema 的 SQLite（空库或已删 ``hotspots`` 行均可，不负责建表）。
差异存在时退出码 1（``--allow-partial`` 降级为 0），配置/IO 错误退出码 2。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.config import config  # noqa: E402
from backend.services.wiki_archiver import (  # noqa: E402
    _parse_feed_records as parse_feed_records,  # 冷层记录契约解析器，与 C2.3a 写入端同源
)

# hotspots 全列（20）— 顺序即 INSERT 占位符顺序，勿随意调整
COLUMNS = (
    "id", "title", "summary", "source", "url", "category", "published_at", "score",
    "fetched_at", "is_fallback", "quality_score", "quality_flags", "quality_checked_at",
    "url_check_status", "ingested_at", "tags", "last_read_at", "lifecycle",
    "is_hidden", "pick_score",
)

REQUIRED = ("title", "source", "url", "category", "published_at", "fetched_at")
VALID_CATEGORIES = {"ai", "ai_security", "security", "finance", "startup", "bid", "github", "tech", "paper"}
SAMPLE_LIMIT = 20


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _json_text(raw: object) -> str:
    """JSON 数组列 → 文本（NULL 归一为 '[]'，与 hotspots 列 NOT NULL DEFAULT '[]' 一致）。"""
    return json.dumps(raw if isinstance(raw, list) else [], ensure_ascii=False)


def _load_cold(wiki_root: Path) -> tuple[list[dict], list[str], int]:
    """扫 ``feed/*.md`` → (records, 月份文件列表, 重复 id 数)。"""
    feed_dir = wiki_root / "feed"
    if not feed_dir.is_dir():
        raise SystemExit(f"[ERROR] 冷层目录不存在: {feed_dir}（先跑 C2.3a 沉降）")

    records: list[dict] = []
    months: list[str] = []
    dup = 0
    seen: set[str] = set()
    for path in sorted(feed_dir.glob("*.md")):
        months.append(path.stem)
        for rec in parse_feed_records(path.read_text(encoding="utf-8")):
            rid = str(rec.get("id") or "").strip()
            if not rid:
                continue
            if rid in seen:
                dup += 1
                continue
            seen.add(rid)
            records.append({**rec, "id": rid})
    return records, months, dup


def _validate(rec: dict) -> list[str]:
    """返回缺失/非法字段名列表（空列表 = 可重建）。"""
    missing = [c for c in REQUIRED if not str(rec.get(c) or "").strip()]
    if "category" not in missing and rec["category"] not in VALID_CATEGORIES:
        missing.append("category(invalid)")
    return missing


def _values(rec: dict) -> tuple:
    return (
        rec["id"],
        str(rec["title"]),
        rec.get("summary") or None,
        str(rec["source"]),
        str(rec["url"]),
        str(rec["category"]),
        str(rec["published_at"]),
        rec.get("score"),
        str(rec["fetched_at"]),
        int(rec.get("is_fallback") or 0),
        int(rec.get("quality_score") or 100),
        _json_text(rec.get("quality_flags")),
        rec.get("quality_checked_at"),
        rec.get("url_check_status"),
        rec.get("ingested_at"),
        _json_text(rec.get("tags")),
        rec.get("last_read_at"),
        rec.get("lifecycle") or "signal",
        int(rec.get("is_hidden") or 0),
        rec.get("pick_score"),
    )


def _upsert_sql(mode: str) -> str:
    cols = ", ".join(COLUMNS)
    holes = ", ".join("?" * len(COLUMNS))
    if mode == "sync":
        return f"INSERT OR IGNORE INTO hotspots ({cols}) VALUES ({holes})"
    sets = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c != "id")
    return (
        f"INSERT INTO hotspots ({cols}) VALUES ({holes}) "
        f"ON CONFLICT(id) DO UPDATE SET {sets}"
    )


def rebuild(db_path: Path, wiki_root: Path, *, mode: str, dry_run: bool) -> dict:
    """执行重建并返回对账摘要（``mode`` ∈ {from-cold, sync}）。"""
    records, months, dup = _load_cold(wiki_root)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = {r["id"] for r in conn.execute("SELECT id FROM hotspots")}
        known_tags = {r["id"] for r in conn.execute("SELECT id FROM tags")}

        stats = {
            "mode": mode, "db": str(db_path), "wiki_root": str(wiki_root),
            "cold_records": len(records), "cold_months": len(months),
            "duplicate_ids": dup, "inserted": 0, "updated": 0, "skipped_existing": 0,
            "invalid": [], "skipped_tag_links": 0, "tag_links": 0,
            "missing_after_rebuild": [], "hotspots_rows": 0, "fts_rows": 0,
            "dry_run": dry_run,
        }
        sql = _upsert_sql(mode)
        valid: list[dict] = []
        for rec in records:
            bad = _validate(rec)
            if bad:
                if len(stats["invalid"]) < SAMPLE_LIMIT:
                    stats["invalid"].append({"id": rec["id"], "missing": bad})
                stats["invalid_count"] = stats.get("invalid_count", 0) + 1
                continue
            valid.append(rec)
            if rec["id"] in existing:
                if mode == "sync":
                    stats["skipped_existing"] += 1
                    continue
                stats["updated"] += 1
            else:
                stats["inserted"] += 1

        if not dry_run and valid:
            now = _now_iso()
            with conn:
                for rec in valid:
                    if mode == "sync" and rec["id"] in existing:
                        continue
                    conn.execute(sql, _values(rec))
                    for link in rec.get("tag_links") or []:
                        tid = str((link or {}).get("tag_id") or "")
                        if tid not in known_tags:
                            stats["skipped_tag_links"] += 1
                            continue
                        conn.execute(
                            "INSERT OR IGNORE INTO hotspot_tags "
                            "(hotspot_id, tag_id, confidence, created_at) VALUES (?, ?, ?, ?)",
                            (rec["id"], tid, float(link.get("confidence") or 1.0), now),
                        )
                        stats["tag_links"] += 1

        stats["hotspots_rows"] = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
        stats["fts_rows"] = conn.execute("SELECT COUNT(*) FROM hotspots_fts").fetchone()[0]

        db_ids = {r["id"] for r in conn.execute("SELECT id FROM hotspots")}
        missing = [r["id"] for r in valid if r["id"] not in db_ids]
        stats["missing_after_rebuild"] = missing[:SAMPLE_LIMIT]
        stats["missing_count"] = len(missing)

        diffs = {
            "invalid_count": stats.get("invalid_count", 0),
            "duplicate_ids": dup,
            "skipped_tag_links": stats["skipped_tag_links"],
            "missing_count": len(missing),
            "fts_mismatch": stats["fts_rows"] != stats["hotspots_rows"],
        }
        stats["diff_total"] = sum(int(v) for v in diffs.values() if not isinstance(v, bool)) + int(diffs["fts_mismatch"])

        if stats["diff_total"] and not dry_run:
            with conn:
                conn.execute(
                    "INSERT INTO wiki_events (ts, kind, wiki_path, db_table, db_row_id, agent, payload) "
                    "VALUES (?, 'rebuild_diff', 'feed/', 'hotspots', '', 'script:rebuild_hot_index', ?)",
                    (_now_iso(), json.dumps({**stats, "diffs": diffs}, ensure_ascii=False)),
                )
    finally:
        conn.close()
    return stats


def main() -> int:
    p = argparse.ArgumentParser(description="从冷层 feed/*.md 重建 hotspots 热索引 (R-17 管道 B)")
    p.add_argument("--from-cold", action="store_true", help="冷层记录覆盖同 id 热层行（默认动作）")
    p.add_argument("--sync", action="store_true", help="增量模式: 跳过已存在 id (INSERT OR IGNORE)")
    p.add_argument("--db", default=str(config.db_path), help="目标 SQLite 路径（默认 config.db_path）")
    p.add_argument("--wiki-root", default=str(config.llm_wiki_v2_path), help="llm-wiki-2.0 根目录")
    p.add_argument("--dry-run", action="store_true", help="只解析与对账, 不写 DB")
    p.add_argument("--allow-partial", action="store_true", help="存在对账差异时仍返回 0")
    p.add_argument("--json", action="store_true", dest="json_out", help="输出 JSON 摘要")
    args = p.parse_args()

    if args.sync and args.from_cold:
        p.error("--sync 与 --from-cold 互斥")
    mode = "sync" if args.sync else "from-cold"
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[ERROR] DB 不存在: {db_path}（本脚本不建表, 请先用已初始化 schema 的库）", file=sys.stderr)
        return 2

    stats = rebuild(db_path, Path(args.wiki_root), mode=mode, dry_run=args.dry_run)
    if args.json_out:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(
            f"[{'DRY-RUN' if stats['dry_run'] else 'OK'}] mode={stats['mode']} "
            f"cold={stats['cold_records']}({stats['cold_months']} 月) "
            f"inserted={stats['inserted']} updated={stats['updated']} "
            f"skipped={stats['skipped_existing']} invalid={stats.get('invalid_count', 0)} "
            f"tag_links={stats['tag_links']}(缺引用 {stats['skipped_tag_links']}) "
            f"hotspots={stats['hotspots_rows']} fts={stats['fts_rows']} "
            f"diff={stats['diff_total']}"
        )
        for item in stats["invalid"]:
            print(f"  invalid: {item['id']} missing={item['missing']}")
        for rid in stats["missing_after_rebuild"]:
            print(f"  missing_after_rebuild: {rid}")

    if stats["diff_total"] and not args.allow_partial:
        print(f"[FAIL] 对账差异 {stats['diff_total']} 项（已写 wiki_events kind=rebuild_diff）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
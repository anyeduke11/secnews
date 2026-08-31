#!/usr/bin/env python3
"""snapshot_for_retirement — 锁定 hotspot 端行数基线, 供 dsh-SecNews 迁移对账用。

背景
----
Phase 7 数据迁移 + 旧系统退役。ts 侧 migrate-from-hotspot.ts 把 hotspot.db
迁到 secnews.db 后, 必须验证行数对得上。

本脚本提供一个**冻结的基线文件**, dsh 端迁移完成后, 用同样的 schema 读
secnews.db, 然后和本基线 diff。要求所有 8 张核心表 + 4 个 wiki 子目录的
行数/文件数 **一一对应**。

输出
----
data/retirement_baseline.json (gitignored, 运行时生成)

    {
      "schema_version": 1,
      "snapshot_at": "2026-08-24T...",
      "hotspot_version": "0.5.0",
      "db_path": "backend/hotspot.db",
      "db_size_bytes": 12345678,
      "table_counts": {
        "hotspots": 3391,
        "favorites": 4,
        ...
      },
      "total_db_rows": 8902,
      "wiki_files": {
        "items":     4149,
        "concepts":    96,
        "inbox":       0,
        "quarantine":  0
      },
      "total_wiki_files": 4245,
      "dsh_verify_command": "..."  # 给 dsh 端的对账 hint
    }

为什么需要单独脚本 (而非用 export_for_dsh.py 的 manifest)
----------------------------------------------------------
- export_for_dsh.py 输出含 blob/json-encoded 字段 + 大 JSON 行, 对账开销大
- retirement_baseline.json 只含**数字**, 可以 git diff / jq 直观对比
- 文档化目的: 让 hotspot 端的"退役基线"成为一个独立 artifact
  (类似 schema_version, 锁了就不能改)

用法
----
::

    # 锁定基线 (写到 data/retirement_baseline.json)
    python scripts/snapshot_for_retirement.py

    # 输出到自定义路径
    python scripts/snapshot_for_retirement.py --out /tmp/baseline.json

    # 干跑 (不写盘, 仅打印)
    python scripts/snapshot_for_retirement.py --dry-run

    # 对账 (比 baseline 与当前 DB 行数)
    python scripts/snapshot_for_retirement.py --verify
    # 0 = 一致, 1 = 不一致, 2 = baseline 缺失

验证
----
- 8 张核心表行数与 2026-08-24 锁定值一致 (见 README.md 顶部 RETIRED banner)
- wiki items 数 = knowledge/items/*.md 数
- wiki concepts 数 = knowledge/concepts/*.md 数
- 总 wiki 文件数 = items + concepts + inbox + quarantine

兼容性
----
- hotspot v0.5.x (本文档写作时): hotspots 3391 / favorites 4 / todos 6 /
  sm2_reviews 3 / annotations 2 / hotspot_tags 5356 / knowledge_concepts 98 /
  knowledge_graph 42 (8 表 8902 行) + wiki items 4149 / concepts 96
  (items>=4149 / concepts>=96，v0.6.3 起以 llm-wiki-2.0 为根，活跃根随采集增长)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# repo root = scripts/../..
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "backend" / "hotspot.db"
DEFAULT_OUT = REPO_ROOT / "data" / "retirement_baseline.json"
# v0.6.3 P4 双根合并: 旧 knowledge/ 根已删, 唯一真相源 = llm-wiki-2.0
# (优先级与 backend/wiki_fs/root.py::resolve_wiki_root 一致: env 覆盖 > 新根)
DEFAULT_WIKI = Path(os.environ.get("HOTSPOT_WIKI_ROOT") or REPO_ROOT / "llm-wiki-2.0")

# 与 scripts/export_for_dsh.py 锁定的 8 张核心表保持一致
CORE_TABLES = [
    "hotspots",
    "favorites",
    "todos",
    "sm2_reviews",
    "annotations",
    "hotspot_tags",
    "knowledge_concepts",
    "knowledge_graph",
]

# wiki FS 子目录 (与 export_for_dsh._copy_wiki 保持一致)
WIKI_SUBDIRS = ["items", "concepts", "inbox", "quarantine"]

# 给 dsh 端的对账 hint 命令模板 (运行时打印, 不实际调用)
DSH_VERIFY_TEMPLATE = """\
# dsh 端迁移完成后, 在 secnews 仓库跑:
node -e "
import('node:sqlite').then({{DatabaseSync}} => {{
  const db = new DatabaseSync('data/secnews.db')
  for (const t of {tables_json}) {{
    const n = db.prepare(`SELECT COUNT(*) FROM \\${{t}}`).get()
    console.log(t.padEnd(22), n['COUNT(*)'])
  }}
  db.close()
}})
"
"""


def _read_version() -> str:
    """从 backend/version.py 读 APP_VERSION, 不强依赖 import。"""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from backend.version import APP_VERSION  # type: ignore

        return APP_VERSION
    except Exception:
        return "unknown"


def _count_table(conn: sqlite3.Connection, table: str) -> int:
    """SELECT COUNT(*) FROM table; 表不存在返回 -1 (而非抛错)。"""
    try:
        return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    except sqlite3.OperationalError:
        return -1


def _count_wiki_subdir(src: Path, subdir: str) -> int:
    """knowledge/<subdir>/*.md 文件数。"""
    sub = src / subdir
    if not sub.exists():
        return 0
    return sum(1 for _ in sub.rglob("*.md"))


def snapshot(db_path: Path, wiki_src: Path) -> dict:
    """采集所有基线数字, 返回 baseline dict (不写盘)。"""
    if not db_path.exists():
        raise FileNotFoundError(f"hotspot.db not found: {db_path}")

    conn = sqlite3.connect(db_path)
    table_counts: dict[str, int] = {}
    for t in CORE_TABLES:
        table_counts[t] = _count_table(conn, t)
    conn.close()

    wiki_files: dict[str, int] = {}
    for sub in WIKI_SUBDIRS:
        wiki_files[sub] = _count_wiki_subdir(wiki_src, sub)

    return {
        "schema_version": 1,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "hotspot_version": _read_version(),
        "db_path": str(db_path.relative_to(REPO_ROOT)),
        "db_size_bytes": db_path.stat().st_size,
        "table_counts": table_counts,
        "total_db_rows": sum(v for v in table_counts.values() if v >= 0),
        "wiki_files": wiki_files,
        "total_wiki_files": sum(wiki_files.values()),
        "tables_locked": CORE_TABLES,
        "wiki_subdirs_locked": WIKI_SUBDIRS,
        "dsh_verify_hint": DSH_VERIFY_TEMPLATE.format(
            tables_json=json.dumps(CORE_TABLES)
        ),
    }


def verify(baseline_path: Path, db_path: Path, wiki_src: Path) -> tuple[int, list[str]]:
    """对比 baseline 与当前 DB / wiki 状态, 返回 (exit_code, diff_lines)。

    exit_code: 0 一致, 1 不一致, 2 baseline 缺失。
    """
    if not baseline_path.exists():
        return 2, [f"ERROR: baseline not found at {baseline_path}"]

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = snapshot(db_path, wiki_src)

    diffs: list[str] = []
    for t in CORE_TABLES:
        b = baseline["table_counts"].get(t)
        c = current["table_counts"].get(t)
        if b != c:
            diffs.append(f"  ✗ {t:<22} baseline={b} current={c}")
        else:
            diffs.append(f"  ✓ {t:<22} {b}")
    for sub in WIKI_SUBDIRS:
        b = baseline["wiki_files"].get(sub)
        c = current["wiki_files"].get(sub)
        if b != c:
            diffs.append(f"  ✗ wiki/{sub:<14} baseline={b} current={c}")
        else:
            diffs.append(f"  ✓ wiki/{sub:<14} {b}")

    rc = 1 if any(line.startswith("  ✗") for line in diffs) else 0
    return rc, diffs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="锁定 hotspot 端行数基线 (供 dsh-SecNews 迁移对账)"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"hotspot.db 路径 (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--wiki-src",
        type=Path,
        default=DEFAULT_WIKI,
        help=f"wiki 真相源目录 (default: {DEFAULT_WIKI})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"基线 JSON 输出路径 (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不写盘, 仅打印 snapshot 内容",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="对比 baseline 与当前 DB/wiki, 不写新 baseline",
    )
    args = parser.parse_args()

    if args.verify:
        rc, diffs = verify(args.out, args.db, args.wiki_src)
        print(f"[verify] baseline: {args.out}")
        for line in diffs:
            print(line)
        print()
        if rc == 0:
            print("[✓] baseline == current (all counts match)")
        elif rc == 1:
            print("[✗] baseline != current (counts drifted, do NOT retire)")
        return rc

    if not args.db.exists():
        print(f"ERROR: hotspot.db not found at {args.db}", file=sys.stderr)
        return 2

    snap = snapshot(args.db, args.wiki_src)

    print(f"[*] DB:           {snap['db_path']}")
    print(f"[*] DB size:      {snap['db_size_bytes']:,} bytes")
    print(f"[*] hotspot ver:  {snap['hotspot_version']}")
    print(f"[*] snapshot at:  {snap['snapshot_at']}")
    print()
    print(f"[*] Table counts ({len(snap['table_counts'])} tables):")
    for t, n in snap["table_counts"].items():
        marker = "✗" if n < 0 else "✓"
        print(f"    {marker} {t:<22} {n:>6} rows")
    print(f"    → total_db_rows: {snap['total_db_rows']}")
    print()
    print(f"[*] Wiki files ({len(snap['wiki_files'])} subdirs):")
    for sub, n in snap["wiki_files"].items():
        print(f"    ✓ {sub:<14} {n:>6} .md files")
    print(f"    → total_wiki_files: {snap['total_wiki_files']}")
    print()

    if args.dry_run:
        print("[i] DRY_RUN: not writing to disk")
        print()
        print("[i] dsh verify hint:")
        for line in snap["dsh_verify_hint"].splitlines():
            print(f"    {line}")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(snap, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[✓] Wrote baseline → {args.out}")
    print()
    print("[i] dsh verify hint (paste in secnews repo):")
    for line in snap["dsh_verify_hint"].splitlines():
        print(f"    {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

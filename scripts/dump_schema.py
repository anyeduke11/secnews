#!/usr/bin/env python3
"""dump_schema — 把 hotspot.db 的 schema 导出为 dsh-SecNews 可消费的 SQL + JSON。

背景
----
Phase 1 (存储层移植) spec 第 207 行: 「迁移策略: 从 hotspot 导出当前 schema →
生成 TypeScript DDL → 逐步迁移」。

dsh 端 `packages/store/src/schema.ts` 需要知道 hotspot 端的 72 张业务表 + 145
个索引 + 3 个 trigger + FTS5 虚表组的完整 DDL, 但 dsh 不能反代 hotspot (dsh
AGENTS.md 明确)。本脚本提供一个**只读**的 schema 转储工具, 让 dsh 端可以:

1. 直接 `exec(ddl.sql)` 在 secnews.db 建表
2. 用 `tables.json` 生成 TypeScript 的 table interface
3. 用 `fks.json` 还原外键约束图
4. 用 `fts_groups.json` 决定哪些 FTS5 表需要 dsh 端 rebuild

输出 (4 个文件, 全部写入 ``data/schema/`` 由 gitignored)::

    data/schema/
    ├── ddl.sql            # 全部 CREATE TABLE/INDEX/VIEW/TRIGGER 按依赖顺序
    ├── tables.json        # 每张表的 dict: type/sql/columns/pk/indexes/fks
    ├── fks.json           # 全表外键关系图 (from_table, from_cols, to_table, to_cols)
    └── fts_groups.json    # FTS5 虚表组 (hotspots_fts + 5 支撑表, wiki_items_fts + 5)
                           # dsh 端可据此跳过 FTS5 重建, 或选择性 rebuild

为什么需要单独脚本 (而非 export_for_dsh.py 的 subcommand)
--------------------------------------------------------
- export_for_dsh.py 关注**数据行**, 不关心 DDL
- dump_schema 关注**结构**, 不导出任何数据行
- 工具拆分: 一个脚本一行职责

用法
----
::

    # 完整导出 (默认到 data/schema/)
    python3 scripts/dump_schema.py

    # 输出到自定义目录
    python3 scripts/dump_schema.py --out /tmp/schema

    # 干跑 (仅打印统计, 不写盘)
    python3 scripts/dump_schema.py --dry-run

    # 仅导出 DDL (简化模式)
    python3 scripts/dump_schema.py --sql-only --out /tmp/sql

兼容性
----
- hotspot v0.5.x: 80 sqlite_master 对象 (72 业务表 + 6 FTS5 虚表 + 4 支撑表 +
  1 sqlite_sequence + 2 sqlite_stat + 1 _migration placeholder + 145 索引 +
  3 trigger + 1 view)
- dsh 端 node:sqlite 支持 PRAGMA table_info / foreign_key_list / index_list,
  与 Python sqlite3 接口对齐
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# repo root = scripts/../..
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "backend" / "hotspot.db"
DEFAULT_OUT = REPO_ROOT / "data" / "schema"

# SQLite 内部表 (非业务表, dsh 端不消费)
SQLITE_INTERNAL_PREFIXES = ("sqlite_",)
PLACEHOLDER_NAMES = {"_migration_056_placeholder"}

# FTS5 虚表支撑表后缀 (FTS5 模块自动生成)
FTS5_SHADOW_SUFFIXES = (
    "_config",
    "_data",
    "_docsize",
    "_idx",
    "_content",  # external content 表 (unified_fts / wiki_items_fts 用)
)


def _read_version() -> str:
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from backend.version import APP_VERSION  # type: ignore

        return APP_VERSION
    except Exception:
        return "unknown"


def _is_internal(name: str) -> bool:
    """sqlite_sequence / sqlite_stat* / sqlite_master 内部表。"""
    return any(name.startswith(p) for p in SQLITE_INTERNAL_PREFIXES)


def _is_fts5_shadow(name: str) -> bool:
    """FTS5 虚表的支撑表 (xxx_config/xxx_data/xxx_docsize/xxx_idx/xxx_content)。"""
    return any(name.endswith(s) for s in FTS5_SHADOW_SUFFIXES)


def _classify_table(name: str) -> str:
    """表分类: 'internal' / 'fts5_shadow' / 'placeholder' / 'business'。"""
    if _is_internal(name):
        return "internal"
    if name in PLACEHOLDER_NAMES:
        return "placeholder"
    if _is_fts5_shadow(name):
        return "fts5_shadow"
    return "business"


def _fetch_all_objects(conn: sqlite3.Connection) -> list[dict[str, str]]:
    """读 sqlite_master 全部对象 (table/index/view/trigger)。"""
    rows = conn.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL ORDER BY type DESC, name"
    ).fetchall()
    return [
        {"type": r[0], "name": r[1], "tbl_name": r[2], "sql": r[3]}
        for r in rows
    ]


def _fetch_table_detail(conn: sqlite3.Connection, table: str) -> dict[str, Any]:
    """取单张表的详细元数据: columns / pk / indexes / fks。"""
    cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    # cols: cid, name, type, notnull, dflt_value, pk

    pk_cols = sorted(
        [(c[5], c[1]) for c in cols if c[5] > 0], key=lambda x: x[0]
    )
    pk = [name for _, name in pk_cols] if pk_cols else []

    idx_rows = conn.execute(f'PRAGMA index_list("{table}")').fetchall()
    # idx_rows: seq, name, unique, origin, partial
    indexes = []
    for ir in idx_rows:
        idx_name = ir[1]
        idx_info = conn.execute(f'PRAGMA index_info("{idx_name}")').fetchall()
        indexes.append(
            {
                "name": idx_name,
                "unique": bool(ir[2]),
                "origin": ir[3],  # 'c' = CREATE INDEX, 'u' = UNIQUE, 'pk' = PRIMARY KEY
                "columns": [c[2] for c in idx_info],
            }
        )

    fk_rows = conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
    # fk_rows: id, seq, table, from, to, on_update, on_delete, match
    fks = [
        {
            "id": r[0],
            "seq": r[1],
            "table": r[2],
            "from": r[3],
            "to": r[4],
            "on_update": r[5],
            "on_delete": r[6],
        }
        for r in fk_rows
    ]

    return {
        "columns": [
            {
                "name": c[1],
                "type": c[2],
                "notnull": bool(c[3]),
                "default": c[4],
                "pk_position": c[5],  # 0 = not part of PK
            }
            for c in cols
        ],
        "pk": pk,
        "indexes": indexes,
        "fks": fks,
    }


def _group_fts5(conn: sqlite3.Connection, objects: list[dict]) -> list[dict]:
    """识别 FTS5 虚表组 (xxx_fts + 5 个支撑表)。

    FTS5 支撑表命名规则: <main_name> + <shadow_suffix>, 其中 main_name 含 "_fts"。
    例: hotspots_fts → hotspots_fts_config / _data / _docsize / _idx。
    注意: 不能用 prefix 匹配, 否则会把 hotspots_audit 等无关 trigger 表算入。
    """
    fts_main = [o for o in objects if o["type"] == "table" and o["name"].endswith("_fts")]
    groups = []
    table_names = {o["name"] for o in objects if o["type"] == "table"}
    for main in fts_main:
        is_fts5 = "USING fts5" in (main["sql"] or "")
        shadow_names = [
            main["name"] + sfx
            for sfx in FTS5_SHADOW_SUFFIXES
            if main["name"] + sfx in table_names
        ]
        groups.append(
            {
                "name": main["name"],
                "shadow_tables": sorted(shadow_names),
                "is_fts5": is_fts5,
                "sql": main["sql"],
            }
        )
    return groups


def dump(db_path: Path) -> dict[str, Any]:
    """采集全部 schema 信息, 返回 dict (不写盘)。"""
    if not db_path.exists():
        raise FileNotFoundError(f"hotspot.db not found: {db_path}")

    conn = sqlite3.connect(db_path)
    objects = _fetch_all_objects(conn)

    # 分类汇总
    by_type: dict[str, list[str]] = {"table": [], "index": [], "view": [], "trigger": []}
    classified: dict[str, str] = {}  # name -> category
    for o in objects:
        by_type.setdefault(o["type"], []).append(o["name"])
        if o["type"] == "table":
            classified[o["name"]] = _classify_table(o["name"])

    # 业务表详情
    business_tables: dict[str, dict] = {}
    for name in sorted(classified):
        if classified[name] != "business":
            continue
        detail = _fetch_table_detail(conn, name)
        business_tables[name] = detail

    # FTS5 组
    fts_groups = _group_fts5(conn, objects)

    # 外键汇总 (扁平)
    all_fks: list[dict] = []
    for name, detail in business_tables.items():
        for fk in detail["fks"]:
            all_fks.append({"from_table": name, **fk})

    # DDL 排序: table → view → trigger → index, 按依赖拓扑 (简化: 按字母)
    ddl_objects = [o for o in objects if o["type"] in ("table", "view", "trigger", "index")]

    return {
        "schema_version": 1,
        "dumped_at": datetime.now(timezone.utc).isoformat(),
        "hotspot_version": _read_version(),
        "db_path": str(db_path.relative_to(REPO_ROOT)),
        "db_size_bytes": db_path.stat().st_size,
        "totals": {
            "all_objects": len(objects),
            "tables": len(by_type.get("table", [])),
            "business_tables": sum(1 for c in classified.values() if c == "business"),
            "fts5_shadow_tables": sum(1 for c in classified.values() if c == "fts5_shadow"),
            "internal_tables": sum(1 for c in classified.values() if c == "internal"),
            "placeholders": sum(1 for c in classified.values() if c == "placeholder"),
            "fts5_groups": len(fts_groups),
            "indexes": len(by_type.get("index", [])),
            "views": len(by_type.get("view", [])),
            "triggers": len(by_type.get("trigger", [])),
            "fks_total": len(all_fks),
        },
        "tables": business_tables,
        "fts_groups": fts_groups,
        "fks_flat": all_fks,
        "ddl_objects": ddl_objects,
    }


def render_ddl(dump_obj: dict[str, Any]) -> str:
    """生成可被 node:sqlite 直接 exec 的 SQL 文件。

    跳过两类对象:
    - FTS5 虚表的支撑表 (config/data/docsize/idx/content): 已被
      ``CREATE VIRTUAL TABLE xxx_fts USING fts5(...)`` 隐式创建
    - sqlite_* 内部表 (sqlite_sequence / sqlite_stat1 等): SQLite 自动维护, 不可手动创建
    """
    skip_tables: set[str] = set()
    for g in dump_obj["fts_groups"]:
        skip_tables.update(g["shadow_tables"])

    lines: list[str] = [
        f"-- hotspot.db schema dump (schema_version={dump_obj['schema_version']})",
        f"-- dumped_at: {dump_obj['dumped_at']}",
        f"-- hotspot_version: {dump_obj['hotspot_version']}",
        f"-- business_tables: {dump_obj['totals']['business_tables']}, "
        f"fts5_groups: {dump_obj['totals']['fts5_groups']}, "
        f"indexes: {dump_obj['totals']['indexes']}, "
        f"triggers: {dump_obj['totals']['triggers']}",
        "",
        "PRAGMA foreign_keys = OFF;",
        "",
    ]
    grouped: dict[str, list[dict]] = {"table": [], "view": [], "trigger": [], "index": []}
    skipped_internal = 0
    for o in dump_obj["ddl_objects"]:
        # 跳过 FTS5 shadow 表与 sqlite_* 内部表
        if o["type"] == "table" and (
            o["name"] in skip_tables or o["name"].startswith("sqlite_")
        ):
            if o["name"].startswith("sqlite_"):
                skipped_internal += 1
            continue
        grouped.setdefault(o["type"], []).append(o)

    for t in ("table", "view", "trigger", "index"):
        items = grouped.get(t, [])
        if not items:
            continue
        skip_note = (
            f"skipping {len(skip_tables)} fts5 shadow + {skipped_internal} sqlite_*"
            if t == "table"
            else ""
        )
        lines.append(f"-- ===== {t.upper()} ({len(items)}{', ' + skip_note if skip_note else ''}) =====")
        for o in items:
            lines.append(o["sql"].rstrip(";") + ";")
        lines.append("")

    lines.append("PRAGMA foreign_keys = ON;")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="导出 hotspot.db schema 为 dsh-SecNews 可消费的 SQL + JSON"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"hotspot.db 路径 (default: {DEFAULT_DB})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"输出目录 (default: {DEFAULT_OUT})")
    parser.add_argument("--dry-run", action="store_true", help="不写盘, 仅打印统计")
    parser.add_argument("--sql-only", action="store_true", help="仅写 ddl.sql (不写 JSON)")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"ERROR: hotspot.db not found at {args.db}", file=sys.stderr)
        return 2

    obj = dump(args.db)
    totals = obj["totals"]

    print(f"[*] DB:           {obj['db_path']}")
    print(f"[*] DB size:      {obj['db_size_bytes']:,} bytes")
    print(f"[*] hotspot ver:  {obj['hotspot_version']}")
    print(f"[*] dumped at:    {obj['dumped_at']}")
    print()
    print("[*] Totals:")
    for k, v in totals.items():
        print(f"    {k:<22} {v}")
    print()
    print(f"[*] Business tables ({totals['business_tables']}):")
    for name in sorted(obj["tables"])[:20]:
        t = obj["tables"][name]
        pk_str = f" PK={','.join(t['pk'])}" if t["pk"] else ""
        idx_str = f" {len(t['indexes'])}idx" if t["indexes"] else ""
        fk_str = f" {len(t['fks'])}fk" if t["fks"] else ""
        print(f"    {name:<32}{pk_str}{idx_str}{fk_str}")
    if totals["business_tables"] > 20:
        print(f"    ... +{totals['business_tables'] - 20} more")
    print()
    print(f"[*] FTS5 groups ({totals['fts5_groups']}):")
    for g in obj["fts_groups"]:
        print(f"    {g['name']:<24} shadow={len(g['shadow_tables'])}")
        for s in g["shadow_tables"]:
            print(f"      └─ {s}")

    if args.dry_run:
        print()
        print("[i] DRY_RUN: not writing to disk")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)

    # 1. ddl.sql
    ddl_path = args.out / "ddl.sql"
    ddl_path.write_text(render_ddl(obj), encoding="utf-8")
    print(f"[✓] Wrote {ddl_path}")

    if args.sql_only:
        return 0

    # 2. tables.json (业务表详情)
    tables_path = args.out / "tables.json"
    tables_payload = {
        "schema_version": obj["schema_version"],
        "dumped_at": obj["dumped_at"],
        "hotspot_version": obj["hotspot_version"],
        "totals": totals,
        "tables": obj["tables"],
    }
    tables_path.write_text(
        json.dumps(tables_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[✓] Wrote {tables_path}")

    # 3. fks.json (外键扁平图)
    fks_path = args.out / "fks.json"
    fks_payload = {
        "schema_version": obj["schema_version"],
        "totals_fks": totals["fks_total"],
        "fks": obj["fks_flat"],
    }
    fks_path.write_text(
        json.dumps(fks_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[✓] Wrote {fks_path}")

    # 4. fts_groups.json (FTS5 虚表组)
    fts_path = args.out / "fts_groups.json"
    fts_payload = {
        "schema_version": obj["schema_version"],
        "totals_groups": totals["fts5_groups"],
        "groups": obj["fts_groups"],
    }
    fts_path.write_text(
        json.dumps(fts_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[✓] Wrote {fts_path}")

    print()
    print("[i] dsh 端消费提示:")
    print("    # 1. 建表")
    print("    node -e \"import('node:sqlite').then(({DatabaseSync}) => {")
    print("      const db = new DatabaseSync('data/secnews.db')")
    print(f"      db.exec(require('fs').readFileSync('{args.out}/ddl.sql', 'utf8'))")
    print("      db.close()\")")
    print("    # 2. 读 tables.json 生成 schema.ts")
    print(f"    # 3. 跳过 FTS5 重建: {totals['fts5_groups']} 组, 见 fts_groups.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

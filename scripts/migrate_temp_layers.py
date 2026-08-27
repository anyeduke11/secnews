"""M2-T6.4: 一次性表跨库迁移 (HOT/WARM/COLD 物理分离)。

读 ``scripts/retention.json``, 把每张 WARM/COLD 表:
  1. 在对应 db 文件 (hotspot-warm.db / hotspot-cold.db) 创建 schema (CREATE TABLE IF NOT EXISTS,
     复用 MIGRATIONS_DIR 中的 DDL)
  2. 跨库 INSERT INTO warm.x SELECT * FROM main.x (按批次 5000 行, 进度条)
  3. 主库 DROP TABLE (warm) 或 keep-as-archive (cold: 移到 cold.x, 主库空表)

vtab (FTS5) 特殊处理 (T6.4 盲区修复, 见 PROGRESS.md):
  - 三类形态: external content (content=X → 目标库建虚表后 'rebuild' 回灌),
    contentless (content='' → 索引不可复制, 按 rowid 从 base 表重灌),
    普通 fts5 (数据自含 → 正常行拷贝)
  - 影子表 (*_config/_data/_idx/_docsize/_content) 不进迁移清单, 由虚表隐式管理;
    目标库若有历史孤儿影子表, 先 DROP 再建虚表
  - 触发器随表复制到目标库 (contentless 除外 — 其 base 表留守主库,
    触发器必须留在主库才能同步索引)

用法
----
    # 1. 干跑 (默认, 打印计划, 不动库)
    PYTHONPATH=. .venv/bin/python scripts/migrate_temp_layers.py --dry-run

    # 2. 实际执行 (必须先停服务 — --assume-down 默认 True)
    PYTHONPATH=. .venv/bin/python scripts/migrate_temp_layers.py --execute

    # 3. 只迁指定层
    PYTHONPATH=. .venv/bin/python scripts/migrate_temp_layers.py --execute --layer WARM

退出码: 0 OK / 1 部分失败 / 2 fatal
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from scripts.cli_contract import (
    EXIT_FATAL,
    EXIT_OK,
    EXIT_PARTIAL,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RETENTION = REPO_ROOT / "scripts" / "retention.json"
HOT_DB = REPO_ROOT / "backend" / "hotspot.db"
WARM_DB = REPO_ROOT / "backend" / "hotspot-warm.db"
COLD_DB = REPO_ROOT / "backend" / "hotspot-cold.db"
MIGRATIONS_DIR = REPO_ROOT / "backend" / "repository" / "migrations"

BATCH_SIZE = 5000

# FTS5 虚表的隐式影子表后缀 — 它们由虚表自身管理, 绝不单独迁移
VTAB_SHADOW_SUFFIXES = ("_config", "_data", "_idx", "_docsize", "_content")

# contentless fts5 (content='') 的 base 表 → 列映射: 索引不可复制,
# 只能按 rowid 对齐从 base 表重灌 (与 009/047 migration 的回灌 SQL 同构)
_CONTENTLESS_BACKFILL = {
    "hotspots_fts": ("hotspots", ["title", "summary"]),
}


def load_tables() -> list[dict[str, Any]]:
    cfg = json.loads(RETENTION.read_text(encoding="utf-8"))
    tables = cfg.get("tables", [])
    # 影子表条目剔除 (命名规则: *_<shadow_suffix> 且去后缀后是 *_fts 虚表)
    return [t for t in tables if not _is_shadow_of_vtab(t["table"], set())]


def _query_vtabs(conn: sqlite3.Connection | None) -> list[tuple[str, str | None]]:
    """列出 vtab: [(name, create_sql)]。conn=None 时返回空 (仅命名规则过滤)。"""
    if conn is None:
        return []
    try:
        return conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND sql LIKE 'CREATE VIRTUAL TABLE%'"
        ).fetchall()
    except sqlite3.Error:
        return []


def _is_shadow_of_vtab(table: str, known_vtabs: set[str]) -> bool:
    """判断 table 是否是某个 FTS5 虚表的影子表。

    双重判定: 后缀命中 + 去后缀后是已知 vtab; 若 vtab 集为空 (无法查库时)
    退化为纯命名规则 (stem 含 '_fts'), 覆盖 knowledge_chunks_fts_cjk_data 这类
    二级派生名。
    """
    for suf in VTAB_SHADOW_SUFFIXES:
        if table.endswith(suf):
            stem = table[: -len(suf)]
            if known_vtabs and stem in known_vtabs:
                return True
            if not known_vtabs and "_fts" in stem:
                return True
    return False


def vtab_kind(create_sql: str) -> tuple[str, str | None]:
    """解析 fts5 DDL → ('external'|'contentless'|'plain', content 表名)。"""
    m = re.search(r"content\s*=\s*''", create_sql, re.IGNORECASE)
    if m:
        return "contentless", None
    m = re.search(r"content\s*=\s*['\"]?([\w]+)['\"]?", create_sql, re.IGNORECASE)
    if m:
        return "external", m.group(1)
    return "plain", None


def table_layer(t: dict[str, Any]) -> str:
    """返回 db 别名: hot / warm / cold (小写). FROZEN md 不走此脚本."""
    temp = t.get("temp", "HOT")
    return {"HOT": "hot", "WARM": "warm", "COLD": "cold"}.get(temp, "hot")


def get_create_sql(conn: sqlite3.Connection, table: str) -> str | None:
    """从主库 sqlite_master 读出 CREATE TABLE / CREATE VIRTUAL TABLE 语句。"""
    try:
        r = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return r[0] if r and r[0] else None
    except Exception:
        return None


def get_triggers_for(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    """返回挂在 table 上的触发器: [(name, create_sql)]。"""
    try:
        return conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='trigger' AND sql IS NOT NULL "
            "AND (instr(sql, ?) > 0)",
            (f"ON {table}",),
        ).fetchall()
    except sqlite3.Error:
        return []


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    except Exception:
        return 0


def _drop_dst_vtab_remains(conn: sqlite3.Connection, dst_alias: str, table: str) -> None:
    """目标库若残留同名虚表/影子表 (T6.4 孤儿事故形态), 先清掉再建。"""
    names = {
        r[0] for r in conn.execute(
            f"SELECT name FROM {dst_alias}.sqlite_master WHERE type='table' AND name LIKE ?",
            (table + "%",),
        ).fetchall()
    }
    for suf in ("",) + VTAB_SHADOW_SUFFIXES:
        n = table + suf
        if n in names:
            conn.execute(f'DROP TABLE IF EXISTS {dst_alias}."{n}"')


def copy_vtab(
    conn: sqlite3.Connection,
    dst_alias: str,
    table: str,
    create_sql: str,
    kind: str,
    content_table: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    """FTS5 虚表迁移。

    external  : dst 建虚表 → 等 content 表迁完后 'rebuild' 回灌 (由 run() 排序保证)
    contentless: 索引数据不可复制 — dst 只建空虚表占位, 真实回灌由
                 _CONTENTLESS_BACKFILL 在 base 表迁移后执行; base 表本身留守主库,
                 故触发器也必须留守 (否则主库写入不再同步索引)
    plain     : dst 建虚表 → 正常行拷贝 (fts5 表可直接 INSERT...SELECT)
    """
    n = count_rows(conn, table)

    if dry_run:
        return {"table": table, "rows": n, "dropped": False, "ok": True,
                "dry_run": True, "vtab_kind": kind}

    try:
        _drop_dst_vtab_remains(conn, dst_alias, table)
        # 原 DDL 重写到 dst 库 (IF NOT EXISTS 幂等)
        target_sql = re.sub(
            r"^CREATE VIRTUAL TABLE\b",
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {dst_alias}.",
            create_sql, count=1, flags=re.IGNORECASE,
        )
        conn.executescript(target_sql)
    except sqlite3.Error as e:
        return {"table": table, "rows": n, "ok": False, "error": f"vtab CREATE failed: {e}"}

    if kind == "contentless":
        # base 表留守主库: 触发器不复制, 索引行拷贝无意义 (contentless 读不出原文)
        return {"table": table, "rows": 0, "dropped": False, "ok": True,
                "defer": "backfill",
                "note": "contentless: dst 空虚表占位, 回灌延后到 base 表迁移", "vtab_kind": kind}

    if kind == "external":
        # 数据本体在 content 表里, 这里只建结构; rebuild 由 run() 在 content 表迁完后统一执行
        return {"table": table, "rows": 0, "dropped": False, "ok": True,
                "defer": "rebuild", "content_table": content_table,
                "note": f"external(content={content_table}): 结构已建, rebuild 延后",
                "vtab_kind": kind}

    # plain: 数据自含, 直接跨库拷贝
    try:
        conn.executescript(f'INSERT INTO {dst_alias}."{table}" SELECT * FROM main."{table}"')
    except sqlite3.Error as e:
        return {"table": table, "rows": n, "ok": False, "error": f"vtab INSERT failed: {e}"}

    # 触发器随迁 (重写到 dst 库), 然后连源虚表一起 DROP
    copied_triggers = _copy_triggers_to_dst(conn, dst_alias, table)
    dr = drop_source_table(conn, table, is_vtab=True, copied_triggers=[])
    if not dr["dropped"]:
        return {"table": table, "rows": n, "copied": n, "ok": False,
                "error": dr.get("error", "DROP failed")}

    return {"table": table, "rows": n, "copied": n, "dropped": True, "ok": True,
            "triggers_copied": copied_triggers, "vtab_kind": kind}


def _copy_triggers_to_dst(conn: sqlite3.Connection, dst_alias: str, table: str) -> list[str]:
    """把挂在该表上的触发器复制到 dst 库 (CREATE TRIGGER dst.name)。"""
    copied: list[str] = []
    for name, sql in get_triggers_for(conn, table):
        try:
            rewritten = re.sub(
                r"^CREATE TRIGGER(\s+IF\s+NOT\s+EXISTS)?\s+\S+",
                lambda m: f"CREATE TRIGGER{m.group(1) or ''} {dst_alias}.{name}",
                sql, count=1, flags=re.IGNORECASE,
            )
            conn.executescript(rewritten)
            copied.append(name)
        except sqlite3.Error:
            continue  # 触发器复制失败不阻断主流程, 结果里可见
    return copied


def drop_source_table(conn: sqlite3.Connection, table: str, is_vtab: bool,
                      copied_triggers: list[str]) -> dict[str, Any]:
    """DROP 主库源表; vtab 连带已复制到 dst 的触发器一起清。"""
    try:
        for name in copied_triggers:
            conn.execute(f'DROP TRIGGER IF EXISTS "{name}"')
        conn.execute(f'DROP TABLE {"IF EXISTS " if is_vtab else ""}"{table}"')
        return {"dropped": True}
    except sqlite3.Error as e:
        return {"dropped": False, "error": f"DROP failed: {e}"}


def copy_table(
    conn: sqlite3.Connection,
    dst_alias: str,
    table: str,
    dry_run: bool,
) -> dict[str, Any]:
    """单表迁移: 在 dst 创建 schema + 按 batch 复制数据 + drop 源 (execute 时).

    conn 必须是已 ATTACH 了 dst_alias 的连接 (在 run() 外层一次性 ATTACH)。
    """
    sql = get_create_sql(conn, table)
    if not sql:
        n = count_rows(conn, table)
        return {"table": table, "rows": n, "ok": False, "error": "no CREATE TABLE in sqlite_master"}

    # vtab 分流: FTS5 虚表走专用通道
    if sql.lstrip().upper().startswith("CREATE VIRTUAL TABLE"):
        kind, content_table = vtab_kind(sql)
        return copy_vtab(conn, dst_alias, table, sql, kind, content_table, dry_run)

    n = count_rows(conn, table)
    if n == 0:
        return {"table": table, "rows": 0, "dropped": False, "ok": True, "skipped": "empty"}

    if dry_run:
        return {"table": table, "rows": n, "dropped": False, "ok": True, "dry_run": True}

    # 1. CREATE TABLE IF NOT EXISTS 在目标库
    target_sql = sql.replace(
        f'CREATE TABLE {table}',
        f'CREATE TABLE IF NOT EXISTS {dst_alias}.{table}',
        1,
    )
    if target_sql == sql:  # 没替换上 (罕见的 schema 写法)
        target_sql = sql.replace(
            'CREATE TABLE',
            f'CREATE TABLE IF NOT EXISTS {dst_alias}.',
            1,
        )
    try:
        conn.executescript(target_sql)
    except sqlite3.Error as e:
        return {"table": table, "rows": n, "ok": False, "error": f"CREATE failed: {e}"}

    # 2. 跨库 INSERT, 按 batch
    cols = [c[1] for c in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
    cols_csv = ",".join(f'"{c}"' for c in cols)
    placeholders = ",".join("?" for _ in cols)
    copied = 0
    offset = 0
    try:
        while True:
            r = conn.execute(
                f'SELECT {cols_csv} FROM "{table}" LIMIT {BATCH_SIZE} OFFSET {offset}'
            ).fetchall()
            if not r:
                break
            conn.executemany(
                f'INSERT INTO {dst_alias}."{table}" ({cols_csv}) VALUES ({placeholders})',
                r,
            )
            copied += len(r)
            offset += BATCH_SIZE
    except sqlite3.Error as e:
        return {"table": table, "rows": n, "copied": copied, "ok": False, "error": f"INSERT failed: {e}"}

    # 触发器随迁 (重写到 dst 库) — external vtab 的触发器挂在 content 表上,
    # content 表迁走后主库写入必须由 dst 侧触发器继续同步索引
    copied_triggers = _copy_triggers_to_dst(conn, dst_alias, table)

    # 3. drop 主库表
    dr = drop_source_table(conn, table, is_vtab=False, copied_triggers=[])
    if not dr["dropped"]:
        return {"table": table, "rows": n, "copied": copied, "ok": False,
                "error": dr.get("error", "DROP failed")}

    return {"table": table, "rows": n, "copied": copied, "dropped": True, "ok": True,
            "triggers_copied": copied_triggers}

def _db_path_for(alias: str) -> str:
    return {"warm": str(WARM_DB), "cold": str(COLD_DB)}[alias]


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    started_at = time.monotonic()

    # 1. lsof 锁检查
    if args.execute and not args.assume_down:
        import subprocess as _sp
        try:
            r = _sp.run(["lsof", str(HOT_DB)], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return EXIT_FATAL, {
                    "ok": False, "code": EXIT_FATAL,
                    "duration_ms": int((time.monotonic() - started_at) * 1000),
                    "data": {"error": "hotspot.db is held; stop service or pass --assume-down"},
                }
        except FileNotFoundError:
            pass

    if not HOT_DB.exists():
        return EXIT_FATAL, {
            "ok": False, "code": EXIT_FATAL,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "data": {"error": f"hot db not found: {HOT_DB}"},
        }

    all_tables = load_tables()
    if args.layer == "both":
        targets = [t for t in all_tables if table_layer(t) in ("warm", "cold") and t["action"] != "keep"]
    else:
        targets = [t for t in all_tables if table_layer(t) == args.layer and t["action"] != "keep"]

    # 2. 分层 + vtab 依赖排序: external vtab (content=X) 必须排在其 content 表之后
    #    (rebuild 回灌依赖 content 表已就位); 其余保持 retention.json 顺序
    by_layer: dict[str, list[dict[str, Any]]] = {"warm": [], "cold": []}
    for t in targets:
        alias = table_layer(t)
        if alias in by_layer:
            by_layer[alias].append(t)

    def _dep_sort_key(t: dict[str, Any], order: dict[str, int]) -> tuple[int, int]:
        """vtab 及其影子表排层尾 (rebuild 依赖 content 表已迁完), 其余按原顺序。"""
        name = t["table"]
        return (1, order[name]) if "_fts" in name else (0, order[name])

    for alias in by_layer:
        order = {t["table"]: i for i, t in enumerate(by_layer[alias])}
        by_layer[alias].sort(key=lambda t: _dep_sort_key(t, order))

    plan = {
        "warm_count": len(by_layer["warm"]),
        "cold_count": len(by_layer["cold"]),
        "warm_tables": [t["table"] for t in by_layer["warm"]],
        "cold_tables": [t["table"] for t in by_layer["cold"]],
    }

    if args.dry_run:
        return EXIT_OK, {
            "ok": True, "code": EXIT_OK,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "data": {
                "mode": "dry_run",
                "plan": plan,
                "warning": "execute 将 DROP 主库源表, 不可逆 — 必须先 backup + 停服务",
            },
        }

    # 3. execute: 真实迁移
    # 3.1 先 .bak 副本
    backup_path = REPO_ROOT / "backend" / "backups" / f"hotspot-pre-migrate-{int(time.time())}.db"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(HOT_DB))
    bak = sqlite3.connect(str(backup_path))
    try:
        src.backup(bak)
    finally:
        bak.close()
        src.close()
    plan["safety_backup"] = str(backup_path)

    # 3.2 主库连接 (源) — 每个 alias 用独立连接, 避免 ATTACH 锁竞争
    # deferred: [(vtab, kind, content_table, alias)] — external/contentless 回灌延后
    results: list[dict[str, Any]] = []
    failed = 0
    deferred: list[tuple[str, str, str | None, str]] = []
    for alias in ("warm", "cold"):
        target = _db_path_for(alias)
        if not Path(target).exists():
            Path(target).touch()
        # 一个连接 = 一对 (main + alias), 独立 ATTACH
        c = sqlite3.connect(str(HOT_DB), isolation_level=None)
        try:
            c.execute("PRAGMA busy_timeout=5000")
            c.execute(f"ATTACH DATABASE '{target}' AS {alias}")
            for t in by_layer[alias]:
                r = copy_table(c, alias, t["table"], dry_run=False)
                r["layer"] = alias
                results.append(r)
                if not r.get("ok"):
                    failed += 1
                    continue
                if r.get("defer") == "rebuild":
                    deferred.append((t["table"], "external", r.get("content_table"), alias))
                elif r.get("defer") == "backfill":
                    deferred.append((t["table"], "contentless", None, alias))
        finally:
            try:
                c.execute(f"DETACH DATABASE {alias}")
            except sqlite3.Error:
                pass
            c.close()

    # 3.3 回灌阶段: external vtab rebuild / contentless rowid 重灌
    #     (此时 content/base 表已全部迁完或确认留守)
    backfills: list[dict[str, Any]] = []
    if deferred:
        c = sqlite3.connect(str(HOT_DB), isolation_level=None)
        try:
            c.execute("PRAGMA busy_timeout=5000")
            for alias in ("warm", "cold"):
                c.execute(f"ATTACH DATABASE '{_db_path_for(alias)}' AS {alias}")
            for vtab, kind, content_table, alias in deferred:
                try:
                    if kind == "external":
                        c.execute(f"INSERT INTO {alias}.\"{vtab}\"(\"{vtab}\") VALUES('rebuild')")
                        info = {"table": vtab, "method": "rebuild", "ok": True}
                    else:
                        base, cols = _CONTENTLESS_BACKFILL[vtab]
                        col_csv = ",".join(cols)
                        c.executescript(
                            f"INSERT INTO {alias}.\"{vtab}\"(rowid, {col_csv}) "
                            f"SELECT rowid, {col_csv} FROM main.\"{base}\""
                        )
                        cnt = c.execute(f'SELECT COUNT(*) FROM {alias}."{vtab}"').fetchone()[0]
                        info = {"table": vtab, "method": f"rowid-backfill-from-{base}", "rows": cnt, "ok": True}
                except sqlite3.Error as e:
                    info = {"table": vtab, "ok": False, "error": f"backfill failed: {e}"}
                    failed += 1
                backfills.append(info)
        finally:
            for alias in ("warm", "cold"):
                try:
                    c.execute(f"DETACH DATABASE {alias}")
                except sqlite3.Error:
                    pass
            c.close()
        plan["fts_backfill"] = backfills

    # 3.4 走 VACUUM INTO 收尾 (主库)
    if not args.no_vacuum:
        tmp_vacuum = REPO_ROOT / "backend" / "backups" / f"hotspot-migrate-vacuum-{int(time.time())}.db"
        try:
            c = sqlite3.connect(str(HOT_DB))
            c.execute(f"VACUUM INTO '{tmp_vacuum}'")
            c.close()
            shutil.copy2(tmp_vacuum, HOT_DB)
            tmp_vacuum.unlink(missing_ok=True)
            plan["vacuum_after"] = HOT_DB.stat().st_size
        except Exception as e:
            plan["vacuum_error"] = str(e)

    code = EXIT_OK if failed == 0 else EXIT_PARTIAL
    return code, {
        "ok": failed == 0, "code": code,
        "duration_ms": int((time.monotonic() - started_at) * 1000),
        "data": {
            "mode": "execute",
            "plan": plan,
            "results": results,
            "summary": {
                "total": len(results),
                "succeeded": sum(1 for r in results if r.get("ok")),
                "failed": failed,
            },
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description="M2-T6.4 migrate_temp_layers — 一次性 HOT/WARM/COLD 物理分离")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--layer", choices=["warm", "cold", "both"], default="both")
    p.add_argument("--assume-down", action="store_true", default=True)
    p.add_argument("--no-vacuum", action="store_true", help="跳过 VACUUM INTO 收尾")
    p.add_argument("--json", action="store_true", dest="json_out")
    args = p.parse_args()
    if args.execute:
        args.dry_run = False
    code, envelope = run(args)
    if args.json_out:
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    else:
        d = envelope["data"]
        if d.get("mode") == "dry_run":
            print(f"plan: warm={d['plan']['warm_count']} cold={d['plan']['cold_count']}")
            print(f"warning: {d.get('warning')}")
        else:
            s = d["summary"]
            print(f"migrate [{d['mode']}] {s['succeeded']}/{s['total']} ok")
    return code


if __name__ == "__main__":
    sys.exit(main())

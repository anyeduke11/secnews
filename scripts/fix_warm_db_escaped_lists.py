#!/usr/bin/env python3
"""愈合 warm 库中被 json.dumps(ensure_ascii=True) 写坏的中文列表列 (默认 --dry-run)。

背景 (2026-08-29 实测):
  - 生产者已修: knowledge_repo.py 4 处 / knowledge_sync.py 5 处 / bookmark_sync.py 1 处
    全部补上 ensure_ascii=False, 新数据不再被写成字面 \\uXXXX。
  - 存量仍在库: knowledge_items.tags 有 3719 行是 `["\\u5199\\u4f5c", ...]` 形态。
  - md 侧已愈合: 8051 个 md 已按 id 精确还原为真实中文 (见
    scripts/fix_wiki_frontmatter_escape.py)。

为什么不跑 full_sync: backend/wiki_fs/root.py:4-6 声明 llm-wiki-2.0/ 是唯一真相根,
"旧 knowledge/ 根不再被写入或读取", 而 knowledge_sync 的同步源恰恰是 knowledge/。
从"非真相根"整体回灌会把 lifecycle / mastery / compiled 等字段一并推回旧值
(审计已把双根并存列为缺陷)。所以这里只按 id 精确改写目标列, 不碰其他字段。

用法::

    python scripts/fix_warm_db_escaped_lists.py            # dry-run (只 SELECT)
    python scripts/fix_warm_db_escaped_lists.py --apply    # 先快照 DB, 再逐行 UPDATE
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.wiki_fs.contract import parse_frontmatter  # noqa: E402  (需先插 sys.path)

DB_PATH = REPO_ROOT / "backend" / "hotspot-warm.db"
ITEMS_DIR = REPO_ROOT / "knowledge" / "items"
# (表, 主键, 待愈合列) —— 只列实测确认含转义的列
TARGETS: list[tuple[str, str, str]] = [
    ("knowledge_items", "id", "tags"),
    ("knowledge_items", "id", "concepts"),
    ("knowledge_items", "id", "tech_stack"),
]
_ESCAPE_MARK = chr(92) + "u"  # 字面 "\u"


def _needs_heal(value: str | None) -> bool:
    return bool(value) and _ESCAPE_MARK in value


def _md_value(item_id: str, column: str) -> list | None:
    """从已愈合的 md 取该列的真实值; md 不存在或无该键返回 None (不猜)。"""
    path = ITEMS_DIR / f"{item_id}.md"
    if not path.is_file():
        return None
    try:
        fm, _body = parse_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    val = fm.get(column)
    if isinstance(val, str):
        # md 里是 flow 数组时契约解析器会给出 list; 万一退化成字符串, 尝试 JSON 化
        try:
            val = json.loads(val)
        except (ValueError, TypeError):
            return None
    return list(val) if isinstance(val, list) else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="真实写入 (缺省即 dry-run, 以 mode=ro 打开)")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    args = ap.parse_args(argv)

    db = args.db if args.db.is_absolute() else REPO_ROOT / args.db
    if not db.is_file():
        print(f"[error] DB 不存在: {db}", file=sys.stderr)
        return 2

    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    plan: list[tuple[str, str, str, str]] = []   # (table, pk, column, new_json)
    missing_md: list[tuple[str, str]] = []
    totals: dict[str, int] = {}

    for table, pk, col in TARGETS:
        try:
            rows = ro.execute(
                f"SELECT {pk} AS k, {col} AS v FROM {table} WHERE {col} IS NOT NULL"
            ).fetchall()
        except sqlite3.Error as e:
            print(f"[warn] 跳过 {table}.{col}: {e}")
            continue
        bad = [r for r in rows if _needs_heal(r["v"])]
        totals[f"{table}.{col}"] = len(bad)
        for r in bad:
            new_val = _md_value(r["k"], col)
            if new_val is None:
                missing_md.append((col, r["k"]))
                continue
            plan.append((table, r["k"], col, json.dumps(new_val, ensure_ascii=False)))
    ro.close()

    print(f"== fix_warm_db_escaped_lists [{'APPLY' if args.apply else 'DRY-RUN'}] ==")
    for key, n in totals.items():
        print(f"  {key:34s} 含转义 {n} 行")
    print(f"可愈合 (md 有对应条目): {len(plan)}")
    print(f"跳过 (md 缺失/无该键): {len(missing_md)}")
    if missing_md[:3]:
        print("  样例:", ", ".join(f"{c}/{i}" for c, i in missing_md[:3]))

    if plan[:2]:
        print("\n样例 (前 2 条):")
        for table, k, col, new in plan[:2]:
            print(f"  {k} .{col} → {new[:70]}")

    if not args.apply:
        print("\n[dry-run] 以 mode=ro 打开, 未产生任何写入。确认后加 --apply。")
        return 0
    if not plan:
        print("无需愈合。")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db.parent / f"{db.name}.bak-esc-{stamp}"
    shutil.copy2(db, backup)
    for suffix in ("-wal", "-shm"):
        side = Path(str(db) + suffix)
        if side.exists():
            shutil.copy2(side, Path(str(backup) + suffix))
    print(f"\nDB 快照: {backup.name}")

    rw = sqlite3.connect(db)
    try:
        with rw:  # 单事务
            for table, k, col, new in plan:
                rw.execute(f"UPDATE {table} SET {col} = ? WHERE id = ?", (new, k))
        rw.execute("PRAGMA optimize")
    except sqlite3.Error as e:
        print(f"[error] 写入失败, 事务已回滚: {e}", file=sys.stderr)
        return 1
    finally:
        rw.close()

    chk = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    left = {}
    for table, _pk, col in TARGETS:
        try:
            left[f"{table}.{col}"] = chk.execute(
                f"SELECT count(*) FROM {table} WHERE instr({col}, ?) > 0", (_ESCAPE_MARK,)
            ).fetchone()[0]
        except sqlite3.Error:
            left[f"{table}.{col}"] = -1
    chk.close()
    print(f"已改写 {len(plan)} 处; 复扫残留: {left}")
    print(f"回滚: cp {backup.name} {db.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

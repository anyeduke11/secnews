#!/usr/bin/env python3
"""回填 ``hotspots_fts`` 缺失的 FTS5 索引行 (默认 --dry-run, 不写库)。

背景 (2026-08-29 实测):
  - ``hotspots`` 4306 行, ``hotspots_fts`` 仅 1273 行 → 覆盖 29.6%。
  - ``hotspots_fts`` 建表为 ``content=''`` 的 **contentless** FTS5 表:
    列值不存储 (``SELECT id`` 返回 NULL), 关联键是 **rowid**;
    contentless 表**不支持** ``INSERT INTO t(t) VALUES('rebuild')``,
    所以只能按 rowid 显式补插。
  - 触发器 ``hotspots_ai/ad/au`` 存在且正确 → 只缺存量回填, 增量一直正常。
  - 每 5 分钟的 ``fts_rebuild_job`` 只 rebuild 了 0 行的死表 ``unified_fts``,
    从不碰 ``hotspots_fts`` — 这就是覆盖率永远修不上来的原因。

用法::

    python scripts/backfill_hotspots_fts.py            # dry-run: 只报缺口
    python scripts/backfill_hotspots_fts.py --apply    # 先快照 DB, 再事务内补插
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "backend" / "hotspot.db"
TABLE = "hotspots_fts"
# 与建表定义一致的索引列 (contentless: 只需写入这三列)
FTS_COLS = ("title", "summary")


def _missing_rowids(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        f"""
        SELECT h.rowid FROM hotspots h
        LEFT JOIN {TABLE} f ON f.rowid = h.rowid
        WHERE f.rowid IS NULL AND h.rowid IS NOT NULL
        ORDER BY h.rowid
        """
    ).fetchall()
    return [r[0] for r in rows]


def _counts(conn: sqlite3.Connection) -> tuple[int, int]:
    return (
        conn.execute("SELECT count(*) FROM hotspots").fetchone()[0],
        conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0],
    )


def _backfill(conn: sqlite3.Connection, rowids: list[int], batch: int = 500) -> int:
    """按 rowid 显式补插。contentless 表无唯一约束冲突路径, 只插缺失集。"""
    cols = ", ".join(FTS_COLS)
    marks = ", ".join("?" for _ in range(len(FTS_COLS) + 1))
    src_sel = f"SELECT rowid, {cols} FROM hotspots WHERE rowid = ?"
    ins = f"INSERT INTO {TABLE}(rowid, {cols}) VALUES ({marks})"
    inserted = 0
    for i in range(0, len(rowids), batch):
        for rid in rowids[i:i + batch]:
            row = conn.execute(src_sel, (rid,)).fetchone()
            if row is None:
                continue
            conn.execute(ins, (row[0], row[1], row[2]))
            inserted += 1
    return inserted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="真实写入 (缺省即 dry-run, 只执行 SELECT)")
    ap.add_argument("--db", type=Path, default=DB_PATH, help=f"目标 DB (默认 {DB_PATH.relative_to(REPO_ROOT)})")
    args = ap.parse_args(argv)

    db = args.db if args.db.is_absolute() else REPO_ROOT / args.db
    if not db.is_file():
        print(f"[error] DB 不存在: {db}", file=sys.stderr)
        return 2

    # mode=ro 打开: dry-run 与计数阶段物理上不可能写入
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        total, indexed = _counts(conn)
        missing = _missing_rowids(conn)
    finally:
        conn.close()

    print(f"== backfill_hotspots_fts [{'APPLY' if args.apply else 'DRY-RUN'}] ==")
    print(f"hotspots={total} {TABLE}={indexed} 覆盖率={indexed / total * 100 if total else 0:.1f}%")
    print(f"待补插 rowid: {len(missing)}")

    if not args.apply:
        print("[dry-run] 以 mode=ro 打开, 未产生任何写入。确认无误后加 --apply。")
        return 0
    if not missing:
        print("无需回填。")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = REPO_ROOT / "backups" / f"hotspot_pre_fts_backfill_{stamp}.db"
    backup.parent.mkdir(exist_ok=True)
    shutil.copy2(db, backup)
    # 连同 WAL/shm 一起快照, 避免回滚时留下不一致的 WAL
    for suffix in ("-wal", "-shm"):
        side = Path(str(db) + suffix)
        if side.exists():
            shutil.copy2(side, Path(str(backup) + suffix))
    print(f"DB 快照: {backup.relative_to(REPO_ROOT)}")

    conn = sqlite3.connect(db)
    try:
        with conn:  # 单事务: 异常自动回滚
            inserted = _backfill(conn, missing)
        conn.execute("PRAGMA optimize")
    except sqlite3.Error as exc:
        print(f"[error] 回填失败, 事务已回滚: {exc}", file=sys.stderr)
        print(f"如需恢复: cp {backup} {db}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    total2, indexed2 = _counts(conn)
    still_missing = len(_missing_rowids(conn))
    conn.close()
    print(f"补插 {inserted} 行 → {TABLE}={indexed2}/{total2}, 覆盖 {indexed2 / total2 * 100 if total2 else 0:.1f}%, 仍缺 {still_missing}")
    print("回滚: 停服务后 cp backups/hotspot_pre_fts_backfill_%s.db %s" % (stamp, db.relative_to(REPO_ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

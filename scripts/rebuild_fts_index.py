#!/usr/bin/env python3
"""rebuild_fts_index.py — ``hotspots_fts`` 碎片回收 (v0.8.8 R-17 C2.6-P0a)。

背景 (2026-11-13 实测):
  - ``hotspots_fts`` 是 ``content=''`` 的 contentless FTS5 表, 靠
    ``hotspots_ai/ad/au`` 三个触发器 (定义于 migrations/124_paper_category.sql)
    与 ``hotspots`` 保持同步。
  - contentless FTS5 的 DELETE **只打墓碑不回收页** → 大批量删行后索引残留
    大量死页。实测: C2.3b 删 37,317 行后 FTS 占 34.64 MB; 同库重建后仅
    **3.90 MB (−30.74 MB)**, 同 6,548 行 / 同 81,797 词元, **零召回损失**。
  - contentless 表不支持 ``INSERT INTO t(t) VALUES('rebuild')`` (无 content
    表可读), 只能 drop + recreate + 显式重灌 (见 scripts/backfill_hotspots_fts.py)。
  - 既有 ``fts_rebuild_job`` (采集尾部链) rebuild 的是 **0 行的死表**
    ``unified_fts``, 从未碰过真正的 ``hotspots_fts`` —— 碎片因此长期无人
    治理; 该 job 已在 v0.8.8 C2.6-P0d 移除。

设计:
  - **单事务原子切换**: SQLite DDL 可事务化, 故在 ``BEGIN IMMEDIATE`` 内完成
    「DROP 触发器 → DROP FTS → CREATE FTS → 全量重灌 → CREATE 触发器」。
    IMMEDIATE 取写锁 → 无并发写入窗口 → 不丢增量, 也**不需要停服**
    (6.5k 行实测 ~0.1-0.7 s, 远小于 ``busy_timeout`` 5 s)。
  - **不牺牲召回**: 完整保留 ``title + summary`` 两列与 ``unicode61`` 分词器
    (v1 方案曾提议去掉 summary, 批判性审查已撤销 —— 收益仅 ≤3.4 MB 且静默降召回)。
  - **可重建即免备份**: FTS 完全由 ``hotspots`` 派生, 属 R-17「可重建」范畴,
    不做 DB 快照 (C2.1 已退役备份链)。
  - **碎片自判**: 默认 ``--check`` 只报告「每行索引字节 / 每行源文本字节」比值
    (稳态 ≈1.5, 碎片态 >10); ``--defrag`` 强制执行并报告前后体积差。

⚠️ 空间回收的两个阶段 (2026-11-13 实测):
  ``dbstat`` 显示的 FTS 体积下降 (35.22 → 3.93 MB) **不等于文件变小** ——
  实测 defrag 后文件仍为 163.08 MB, 必须再跑 ``VACUUM`` 才降到 131.05 MB。
  根因: ``auto_vacuum=0`` 下 FTS 释放的页只进 freelist, 不还给文件系统。
  故本脚本默认在 defrag 后执行 ``PRAGMA incremental_vacuum``
  (见 C2.6-P0c: 把 ``auto_vacuum`` 切到 INCREMENTAL 后即可在线回收);
  若库仍是 ``auto_vacuum=0``, 会如实报告"索引已整理, 文件需 VACUUM 才缩"。

用法::

    python scripts/rebuild_fts_index.py            # check: 只报碎片指标
    python scripts/rebuild_fts_index.py --defrag   # 执行回收 (+ 在线空间回收)
    python scripts/rebuild_fts_index.py --defrag --json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# 与 migrations/124_paper_category.sql 保持一致 (带旧值删除, 修好静默残留)
FTS_DDL = (
    "CREATE VIRTUAL TABLE hotspots_fts USING fts5("
    "id UNINDEXED, title, summary, content='', tokenize='unicode61')"
)
TRIGGERS = (
    "hotspots_ai",
    "hotspots_ad",
    "hotspots_au",
)
_TRIGGER_DDL = {
    "hotspots_ai": (
        "CREATE TRIGGER hotspots_ai AFTER INSERT ON hotspots BEGIN "
        "INSERT INTO hotspots_fts(rowid, title, summary) "
        "VALUES (new.rowid, new.title, IFNULL(new.summary, '')); END"
    ),
    "hotspots_ad": (
        "CREATE TRIGGER hotspots_ad AFTER DELETE ON hotspots BEGIN "
        "INSERT INTO hotspots_fts(hotspots_fts, rowid, title, summary) "
        "VALUES ('delete', old.rowid, old.title, IFNULL(old.summary, '')); END"
    ),
    "hotspots_au": (
        "CREATE TRIGGER hotspots_au AFTER UPDATE ON hotspots BEGIN "
        "INSERT INTO hotspots_fts(hotspots_fts, rowid, title, summary) "
        "VALUES ('delete', old.rowid, old.title, IFNULL(old.summary, '')); "
        "INSERT INTO hotspots_fts(rowid, title, summary) "
        "VALUES (new.rowid, new.title, IFNULL(new.summary, '')); END"
    ),
}

# 碎片判据: 每行索引字节 / 每行源文本字节。稳态 ≈1.5, 碎片态 >10。
DEFRAG_RATIO_THRESHOLD = 3.0
# 绝对门槛: 太小的库 (新库/测试库) dbstat 对 FTS 影子表统计不可靠,
# 且回收收益微不足道 —— 双重条件避免误判 (实测: 30k 行小库 ratio 可低至 0.01)。
DEFRAG_MIN_BYTES = 4 * 1024 * 1024


def _fts_bytes(conn: sqlite3.Connection) -> int:
    """FTS 相关页总字节 (data/idx/docsize/config 四个影子表之和)。"""
    row = conn.execute(
        "SELECT COALESCE(SUM(pgsize), 0) FROM dbstat WHERE name LIKE 'hotspots_fts%'"
    ).fetchone()
    return int(row[0])


def _source_bytes(conn: sqlite3.Connection) -> int:
    """被索引的源文本字节 (title + IFNULL(summary,''))。"""
    row = conn.execute(
        "SELECT COALESCE(SUM(LENGTH(title) + LENGTH(IFNULL(summary, ''))), 0) "
        "FROM hotspots"
    ).fetchone()
    return int(row[0])


def _counts(conn: sqlite3.Connection) -> tuple[int, int]:
    return (
        conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM hotspots_fts").fetchone()[0],
    )


def fragmentation(db_path: Path) -> dict:
    """只读测量碎片指标 (mode=ro, 物理上不可能写库)。"""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        n_src, n_fts = _counts(conn)
        fts_b, src_b = _fts_bytes(conn), _source_bytes(conn)
        ratio = (fts_b / src_b) if src_b else 0.0
        return {
            "hotspots_rows": n_src,
            "fts_rows": n_fts,
            "fts_bytes": fts_b,
            "source_bytes": src_b,
            "ratio": round(ratio, 2),
            "needs_defrag": (
                ratio > DEFRAG_RATIO_THRESHOLD
                and fts_b > DEFRAG_MIN_BYTES
                and n_fts == n_src
            ),
            "row_mismatch": n_fts != n_src,
        }
    finally:
        conn.close()


def _db_file_bytes(db_path: Path) -> int:
    """DB 主文件 + WAL + SHM 的实际磁盘占用 (文件层面真值)。"""
    total = db_path.stat().st_size
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.exists():
            total += side.stat().st_size
    return total


def _auto_vacuum(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA auto_vacuum").fetchone()[0])


def defrag(db_path: Path, *, reclaim_space: bool = True) -> dict:
    """事务内原子重建 FTS 索引; 随后尝试在线回收文件空间。

    两阶段语义 (2026-11-13 实测):
      1. defrag 让 ``dbstat`` 口径的 FTS 体积从碎片态回到稳态;
      2. 但 ``auto_vacuum=0`` 时**文件不会缩小** —— 需 ``incremental_vacuum``
         (要求 auto_vacuum=INCREMENTAL, 即 C2.6-P0c) 或显式 VACUUM。
    """
    file_before = _db_file_bytes(db_path)
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.row_factory = None
    before = {
        "fts_bytes": _fts_bytes(conn),
        "counts": _counts(conn),
        "auto_vacuum": _auto_vacuum(conn),
    }
    started = datetime.now(timezone.utc)
    reclaimed_pages = 0
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        # IMMEDIATE: 取写锁, 消除「触发器缺失窗口」内的并发写入
        conn.execute("BEGIN IMMEDIATE")
        try:
            for name in TRIGGERS:
                conn.execute(f"DROP TRIGGER IF EXISTS {name}")
            conn.execute("DROP TABLE IF EXISTS hotspots_fts")
            conn.execute(FTS_DDL)
            conn.execute(
                "INSERT INTO hotspots_fts(rowid, title, summary) "
                "SELECT rowid, title, IFNULL(summary, '') FROM hotspots"
            )
            for name in TRIGGERS:
                conn.execute(_TRIGGER_DDL[name])
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        after = {
            "fts_bytes": _fts_bytes(conn),
            "counts": _counts(conn),
        }
        # 阶段 2: 把 freelist 页还给文件系统 (仅 INCREMENTAL/FULL 模式有效)
        if reclaim_space and before["auto_vacuum"] != 0:
            try:
                cur = conn.execute("PRAGMA incremental_vacuum(2000)")
                reclaimed_pages = len(cur.fetchall()) if cur.description else 0
            except sqlite3.Error:
                pass
        return {
            "ok": True,
            "started_at": started.isoformat(),
            "duration_ms": int(
                (datetime.now(timezone.utc) - started).total_seconds() * 1000
            ),
            "before": before,
            "after": after,
            "saved_bytes": before["fts_bytes"] - after["fts_bytes"],
            "file_bytes_before": file_before,
            "file_bytes_after": _db_file_bytes(db_path),
            "reclaimed_pages": reclaimed_pages,
            "needs_vacuum": bool(reclaim_space and before["auto_vacuum"] == 0),
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="hotspots_fts 碎片回收 (R-17 C2.6-P0a)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--db", default=None, help="目标 DB (默认 config.db_path)")
    p.add_argument("--defrag", action="store_true", help="执行回收 (缺省只检查)")
    p.add_argument("--force", action="store_true", help="碎片比未超阈值也执行")
    p.add_argument("--json", action="store_true", dest="json_out")
    args = p.parse_args(argv)

    db_path = Path(args.db) if args.db else None
    if db_path is None:
        from backend.config import config

        db_path = Path(config.db_path)
    if not db_path.is_file():
        print(f"[ERROR] DB 不存在: {db_path}", file=sys.stderr)
        return 2

    frag = fragmentation(db_path)
    if not args.defrag:
        if args.json_out:
            print(json.dumps({"mode": "check", "db": str(db_path), **frag},
                             ensure_ascii=False, indent=2))
        else:
            print(
                f"[check] rows={frag['hotspots_rows']} fts_rows={frag['fts_rows']} "
                f"fts={frag['fts_bytes'] / 1048576:.2f}MB src={frag['source_bytes'] / 1048576:.2f}MB "
                f"ratio={frag['ratio']} (阈值 {DEFRAG_RATIO_THRESHOLD}) "
                f"{'→ 建议回收' if frag['needs_defrag'] else '→ 无需回收'}"
            )
            if frag["row_mismatch"]:
                print("[WARN] hotspots 与 FTS 行数不一致 (触发器失同步?), 回收将修复")
        return 0

    if not frag["needs_defrag"] and not args.force:
        msg = (
            f"碎片比 {frag['ratio']} 未超阈值 {DEFRAG_RATIO_THRESHOLD}, 跳过 "
            f"(确认要执行加 --force)"
        )
        if args.json_out:
            print(json.dumps({"mode": "skipped", "db": str(db_path), **frag,
                              "reason": msg}, ensure_ascii=False, indent=2))
        else:
            print(f"[skip] {msg}")
        return 0

    stats = defrag(db_path)
    saved_mb = stats["saved_bytes"] / 1048576
    file_saved_mb = (stats["file_bytes_before"] - stats["file_bytes_after"]) / 1048576
    if args.json_out:
        print(json.dumps({"mode": "defrag", "db": str(db_path), **stats,
                          "fragmentation_before": frag},
                         ensure_ascii=False, indent=2, default=str))
    else:
        b, a = stats["before"], stats["after"]
        print(
            f"[defrag] FTS {b['fts_bytes'] / 1048576:.2f}MB → {a['fts_bytes'] / 1048576:.2f}MB "
            f"(索引整理 {saved_mb:.2f}MB) | 文件 "
            f"{stats['file_bytes_before'] / 1048576:.2f}MB → "
            f"{stats['file_bytes_after'] / 1048576:.2f}MB "
            f"(回收 {file_saved_mb:.2f}MB)"
            f" rows={a['counts'][0]}/{a['counts'][1]} {stats['duration_ms']}ms"
        )
        if stats.get("needs_vacuum"):
            print(
                "[hint] auto_vacuum=0 → 文件未缩小; 索引已整理但空间仍在 freelist。\n"
                "       切到 INCREMENTAL (C2.6-P0c) 后可在线回收, 或择机跑一次 VACUUM。"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

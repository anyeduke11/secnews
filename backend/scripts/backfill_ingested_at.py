"""离线回填脚本: hotspots.ingested_at 补 NULL + is_hidden 推导 (v0.5 M1-Task1)。

配合迁移 ``064_list_query_optimization.sql`` 使用 — 迁移只加列建索引
(启动时同步执行, 禁止回填), 存量数据由本脚本离线补齐:

1. ``ingested_at`` 回填: ``ingested_at IS NULL AND published_at IS NOT NULL``
   的行用 ``published_at`` 填充 (真实库仅 1 行命中)。
2. ``is_hidden`` 推导: quality_flags 含 historical_bid /
   historical_published / no_published_at / landing_page_unresolvable
   任一 → 1, 否则 0 (与旧 query() 的 4 个 NOT LIKE 过滤口径一致)。

特性:
- 分批处理 (每批 5000 行 + COMMIT + 进度打印), 避免长事务锁库。
- 幂等可重跑: 只更新与目标状态不一致的行, 重复运行 0 行命中。
- 直接用 sqlite3 连 ``backend/hotspot.db`` (不依赖服务连接池)。

用法:
    cd /Users/duke/Documents/hotspot
    .venv/bin/python backend/scripts/backfill_ingested_at.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "hotspot.db"
BATCH_SIZE = 5000

# 与旧 query() 的 NOT LIKE 过滤 / 迁移 064 注释口径一致。
_HIDDEN_FLAG_LIKES = (
    "quality_flags LIKE '%historical_bid%'"
    " OR quality_flags LIKE '%historical_published%'"
    " OR quality_flags LIKE '%no_published_at%'"
    " OR quality_flags LIKE '%landing_page_unresolvable%'"
)


def backfill_ingested_at(conn: sqlite3.Connection) -> int:
    """ingested_at 为 NULL 且 published_at 非 NULL 的行回填为 published_at。"""
    total = 0
    while True:
        conn.execute("BEGIN")
        cur = conn.execute(
            """
            UPDATE hotspots SET ingested_at = published_at
            WHERE rowid IN (
                SELECT rowid FROM hotspots
                WHERE ingested_at IS NULL AND published_at IS NOT NULL
                LIMIT ?
            )
            """,
            (BATCH_SIZE,),
        )
        conn.execute("COMMIT")
        affected = cur.rowcount
        total += affected
        print(f"[ingested_at] 本批回填 {affected} 行 (累计 {total})")
        if affected < BATCH_SIZE:
            break
    return total


def backfill_is_hidden(conn: sqlite3.Connection) -> tuple[int, int]:
    """按 quality_flags 推导 is_hidden, 双向修正 (置 1 / 清 0)。"""
    hidden_total = 0
    while True:
        conn.execute("BEGIN")
        cur = conn.execute(
            f"""
            UPDATE hotspots SET is_hidden = 1
            WHERE rowid IN (
                SELECT rowid FROM hotspots
                WHERE is_hidden != 1 AND ({_HIDDEN_FLAG_LIKES})
                LIMIT ?
            )
            """,
            (BATCH_SIZE,),
        )
        conn.execute("COMMIT")
        affected = cur.rowcount
        hidden_total += affected
        print(f"[is_hidden=1] 本批修正 {affected} 行 (累计 {hidden_total})")
        if affected < BATCH_SIZE:
            break

    visible_total = 0
    while True:
        conn.execute("BEGIN")
        cur = conn.execute(
            f"""
            UPDATE hotspots SET is_hidden = 0
            WHERE rowid IN (
                SELECT rowid FROM hotspots
                WHERE is_hidden != 0 AND NOT ({_HIDDEN_FLAG_LIKES})
                LIMIT ?
            )
            """,
            (BATCH_SIZE,),
        )
        conn.execute("COMMIT")
        affected = cur.rowcount
        visible_total += affected
        print(f"[is_hidden=0] 本批修正 {affected} 行 (累计 {visible_total})")
        if affected < BATCH_SIZE:
            break

    return hidden_total, visible_total


def main() -> int:
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}")
        return 1

    conn = sqlite3.connect(str(DB_PATH), isolation_level=None, timeout=10.0)
    try:
        # 前置检查: is_hidden 列必须已由迁移 064 创建。
        cols = {row[1] for row in conn.execute("PRAGMA table_info(hotspots)")}
        if "is_hidden" not in cols:
            print(
                "hotspots.is_hidden 列不存在 — 请先启动一次服务执行迁移 064 "
                "(或手工 apply backend/repository/migrations/"
                "064_list_query_optimization.sql) 后再跑本脚本。"
            )
            return 1

        total_rows = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
        print(f"开始回填: {DB_PATH} (hotspots 共 {total_rows} 行)")

        n_ingested = backfill_ingested_at(conn)
        n_hidden, n_visible = backfill_is_hidden(conn)

        null_left = conn.execute(
            "SELECT COUNT(*) FROM hotspots WHERE ingested_at IS NULL"
        ).fetchone()[0]
        mismatch_left = conn.execute(
            f"""
            SELECT COUNT(*) FROM hotspots
            WHERE (is_hidden = 1 AND NOT ({_HIDDEN_FLAG_LIKES}))
               OR (is_hidden = 0 AND ({_HIDDEN_FLAG_LIKES}))
            """
        ).fetchone()[0]

        print(
            f"完成: ingested_at 回填 {n_ingested} 行 | is_hidden 置1 "
            f"{n_hidden} 行 / 清0 {n_visible} 行"
        )
        print(f"校验: ingested_at 仍为 NULL {null_left} 行 | is_hidden 不一致 {mismatch_left} 行")
        if null_left or mismatch_left:
            print("存在未收敛数据 (published_at 也为 NULL 的行无法回填 ingested_at)")
            return 2
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

"""Phase 34 (2026-07-08): 一次性清理投资界历史非资讯条目.

清理两类:
1. 投资界源里 URL 路径匹配黑名单的条目 (video/media/{YYYY}investor|{YYYY}s50|{YYYY}f40/uhk/events 子域)
2. 标题含"投资人排行榜"系列的条目 (兜底,即使 URL 不在黑名单)

执行前会 dry-run 打印待删条目,确认后加 --apply 真正删除。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "backend" / "hotspot.db"

DELETE_SQL = """
DELETE FROM hotspots
WHERE source = '投资界'
  AND (
    url LIKE '%/video/%'
    OR url LIKE '%/media/%'
    OR url LIKE '%pedaily.cn/%investor%'
    OR url LIKE '%pedaily.cn/%S50%'
    OR url LIKE '%pedaily.cn/%F40%'
    OR url LIKE '%pedaily.cn/uhk%'
    OR url LIKE '%pedaily.cn/2023STIE%'
    OR url LIKE '%events.pedaily.cn%'
    OR title LIKE '%投资界TOP100%'
    OR title LIKE '%投资界S50%'
    OR title LIKE '%F40中国青年投资人%'
    OR title LIKE '%独角兽榜单%'
    OR title LIKE '%投资界科创100%'
  )
"""

COUNT_SQL = f"""
SELECT COUNT(*) FROM hotspots
WHERE source = '投资界'
  AND (
    url LIKE '%/video/%'
    OR url LIKE '%/media/%'
    OR url LIKE '%pedaily.cn/%investor%'
    OR url LIKE '%pedaily.cn/%S50%'
    OR url LIKE '%pedaily.cn/%F40%'
    OR url LIKE '%pedaily.cn/uhk%'
    OR url LIKE '%pedaily.cn/2023STIE%'
    OR url LIKE '%events.pedaily.cn%'
    OR title LIKE '%投资界TOP100%'
    OR title LIKE '%投资界S50%'
    OR title LIKE '%F40中国青年投资人%'
    OR title LIKE '%独角兽榜单%'
    OR title LIKE '%投资界科创100%'
  )
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="真正删除 (默认 dry-run)")
    parser.add_argument("--db", default=str(DB_PATH), help=f"DB 路径 (默认: {DB_PATH})")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"ERROR: db not found: {args.db}", file=sys.stderr)
        return 1

    con = sqlite3.connect(args.db)
    try:
        before = con.execute("SELECT COUNT(*) FROM hotspots WHERE source='投资界'").fetchone()[0]
        to_delete = con.execute(COUNT_SQL).fetchone()[0]
        print(f"投资界 当前总数: {before}")
        print(f"待删除:        {to_delete}")
        print(f"保留:          {before - to_delete}")
        print()
        if not args.apply:
            print("(dry-run 模式) 加 --apply 真正删除")
            return 0
        cur = con.execute(DELETE_SQL)
        con.commit()
        after = con.execute("SELECT COUNT(*) FROM hotspots WHERE source='投资界'").fetchone()[0]
        print(f"已删除 {cur.rowcount} 条")
        print(f"投资界 删除后:  {after}")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())

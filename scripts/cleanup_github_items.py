"""清理 DB 中 github 分类的非项目链接 items。

保留：URL 是 ``https://github.com/{owner}/{repo}`` 格式的真实项目链接。
删除：导航 / footer / topics / docs / 外部站点等非项目链接。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "hotspot.db"

# 复用 collector 中的过滤器
sys.path.insert(0, str(DB_PATH.parent.parent))
from backend.collectors.github_collector import _is_repo_url  # noqa: E402


def main() -> int:
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, url FROM hotspots WHERE category='github' ORDER BY id"
    ).fetchall()
    print(f"github items in DB: {len(rows)}")

    keep: list[sqlite3.Row] = []
    delete: list[sqlite3.Row] = []
    for r in rows:
        if _is_repo_url(r["url"]):
            keep.append(r)
            print(f"  KEEP  {r['id']}: {r['url']}")
        else:
            delete.append(r)
            print(f"  DEL   {r['id']}: {r['url']}")

    print()
    print(f"Keep: {len(keep)}, Delete: {len(delete)}")

    if "--apply" not in sys.argv:
        print("Dry-run mode. Re-run with --apply to delete non-repo items.")
        conn.close()
        return 0

    for r in delete:
        # 删 hotspots 主表 — FTS5 同步由触发器自动处理
        conn.execute("DELETE FROM hotspots WHERE id = ?", (r["id"],))
    conn.commit()
    print(f"Applied: deleted {len(delete)} non-repo items")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

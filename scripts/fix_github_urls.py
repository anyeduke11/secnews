"""检查并修复 DB 中 github 分类的错误 URL。

错误模式: ``https://github.com/trending/projects/{i}``
正确模式: ``https://github.com/{owner}/{repo}`` (从 title 提取)
"""
from __future__ import annotations

import sqlite3
import re
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "hotspot.db"
OWNER_REPO_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9_.-]+)")


def extract_repo_url(title: str) -> str | None:
    m = OWNER_REPO_RE.match(title.strip())
    if m:
        owner, repo = m.group(1), m.group(2)
        repo = repo.rstrip("/").removesuffix(".git")
        return f"https://github.com/{owner}/{repo}"
    return None


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

    bad: list[tuple[str, str, str, str]] = []  # (id, title, old_url, new_url)
    for r in rows:
        url = r["url"]
        title = r["title"]
        if "github.com/trending/projects/" in url:
            new_url = extract_repo_url(title)
            if new_url:
                bad.append((r["id"], title, url, new_url))
                print(f"  BAD  {r['id']}")
                print(f"       title: {title[:60]}")
                print(f"       old:   {url}")
                print(f"       new:   {new_url}")
            else:
                print(f"  SKIP {r['id']}: cannot extract from title")
        else:
            print(f"  OK   {r['id']}: {url}")

    print()
    print(f"Total bad URLs: {len(bad)}")
    if not bad:
        print("Nothing to fix.")
        return 0

    if "--apply" in sys.argv:
        for id_, _, _, new_url in bad:
            conn.execute(
                "UPDATE hotspots SET url = ? WHERE id = ?",
                (new_url, id_),
            )
        conn.commit()
        print(f"Applied: updated {len(bad)} rows")
    else:
        print("Dry-run mode. Re-run with --apply to update DB.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

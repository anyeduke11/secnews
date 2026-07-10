"""查找 url 重复的 ai items（用户截图中的两张卡片）"""
import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "hotspot.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, title, summary, url, source, quality_flags, quality_score
        FROM hotspots
        WHERE url IN (
            SELECT url FROM hotspots WHERE category='ai' GROUP BY url HAVING COUNT(*) > 1
        )
        ORDER BY url, id
    """).fetchall()
    print(f"url 重复的 ai items: 总 {len(rows)} 条")
    seen_urls = set()
    for r in rows:
        if r["url"] not in seen_urls:
            print()
            seen_urls.add(r["url"])
        print(f"  id={r['id']}")
        print(f"  title: {r['title'][:80]}")
        print(f"  url:   {r['url']}")
        print(f"  flags: {r['quality_flags']}")
        print(f"  score: {r['quality_score']}")
    conn.close()


if __name__ == "__main__":
    main()

"""查找真实抓取数据中 url 重复且 title 不同的 items(用户截图场景)"""
import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "hotspot.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # 排除 chaos 测试数据
    rows = conn.execute("""
        SELECT id, title, url, source, quality_flags, quality_score
        FROM hotspots
        WHERE url IN (
            SELECT url FROM hotspots
            WHERE category='ai' AND id NOT LIKE 'chaos_%'
            GROUP BY url HAVING COUNT(*) > 1
        )
        AND id NOT LIKE 'chaos_%'
        ORDER BY url, id
    """).fetchall()
    print(f"真实数据 url 重复的 ai items: 总 {len(rows)} 条")
    seen_urls = set()
    for r in rows:
        if r["url"] not in seen_urls:
            print()
            seen_urls.add(r["url"])
        print(f"  id={r['id']}")
        print(f"  title: {r['title']}")
        print(f"  url:   {r['url']}")
        print(f"  source: {r['source']}")
        print(f"  flags: {r['quality_flags']}")
        print(f"  score: {r['quality_score']}")
    conn.close()


if __name__ == "__main__":
    main()

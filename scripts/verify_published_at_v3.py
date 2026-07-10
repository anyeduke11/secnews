"""检查历史日期数据的来源"""
import sqlite3
import sys
from pathlib import Path

db_path = Path("backend/hotspot.db")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

print("=== Items with published_at NOT equal fetched_at (top 10) ===")
rows = conn.execute(
    """SELECT title, published_at, fetched_at, is_fallback, source, category,
              substr(url, 1, 60) AS url_short
       FROM hotspots
       WHERE published_at != fetched_at
       ORDER BY published_at DESC LIMIT 10"""
).fetchall()
for r in rows:
    print(f"  [{r['category']}/{r['is_fallback']}] pub={r['published_at'][:19]}")
    print(f"  fetch={r['fetched_at'][:19]}  source={r['source']}")
    print(f"  title={r['title'][:50]}")
    print(f"  url={r['url_short']}")
    print()

print("=== Count: published_at = fetched_at (same) ===")
same = conn.execute(
    "SELECT COUNT(*) FROM hotspots WHERE published_at = fetched_at"
).fetchone()[0]
diff = conn.execute(
    "SELECT COUNT(*) FROM hotspots WHERE published_at != fetched_at"
).fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]
print(f"  same={same}  diff={diff}  total={total}")

print()
print("=== Latest items with is_fallback=0 (top 5) ===")
rows = conn.execute(
    """SELECT title, published_at, fetched_at, source, substr(url, 1, 50) AS url_short
       FROM hotspots WHERE is_fallback=0
       ORDER BY fetched_at DESC LIMIT 5"""
).fetchall()
for r in rows:
    print(f"  fetch={r['fetched_at'][:19]} pub={r['published_at'][:19]} source={r['source']}")
    print(f"  title={r['title'][:50]} url={r['url_short']}")

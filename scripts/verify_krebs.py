"""检查 Krebs 抓取是否现在有真实 published_at"""
import sqlite3
import sys
from pathlib import Path

db_path = Path("backend/hotspot.db")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

print("=== Top 10 most recent items (all categories) by fetched_at ===")
rows = conn.execute(
    """SELECT category, title, published_at, fetched_at, is_fallback, source,
              substr(url, 1, 60) AS url_short
       FROM hotspots
       ORDER BY fetched_at DESC LIMIT 10"""
).fetchall()
for r in rows:
    delta = r["fetched_at"][:19]
    pub = r["published_at"][:19]
    diff = "SAME" if r["published_at"] == r["fetched_at"] else "DIFF"
    print(f"  [{r['category']}/{r['is_fallback']}] {diff}")
    print(f"  pub={pub} fetch={delta}")
    print(f"  source={r['source']}")
    print(f"  title={r['title'][:50]}")
    print(f"  url={r['url_short']}")
    print()

print("=== Top 10 by published_at DESC (most recent real timestamps) ===")
rows = conn.execute(
    """SELECT category, title, published_at, fetched_at, is_fallback, source
       FROM hotspots WHERE is_fallback=0
       ORDER BY published_at DESC LIMIT 10"""
).fetchall()
for r in rows:
    print(f"  [{r['category']}] pub={r['published_at'][:19]}  {r['title'][:50]}")
    print(f"    source={r['source']}")

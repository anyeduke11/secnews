"""一次性脚本: 检查最近抓取的 published_at 是否真实 (Bug 2 验证)"""
import sqlite3
import sys
from pathlib import Path

db_path = Path("backend/hotspot.db")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

print("=== Top 5 most recent AI items by fetched_at ===")
rows = conn.execute(
    """SELECT title, published_at, fetched_at, is_fallback, source,
              substr(url, 1, 50) AS url_short
       FROM hotspots WHERE category='ai' AND is_fallback=0
       ORDER BY fetched_at DESC LIMIT 5"""
).fetchall()
for r in rows:
    print(f"  fetched_at={r['fetched_at']}")
    print(f"  pub={r['published_at']}")
    print(f"  title={r['title'][:50]}")
    print(f"  url={r['url_short']}")
    print()

print("=== published_at distribution (ALL non-fallback) ===")
rows = conn.execute(
    """SELECT date(published_at) AS day, COUNT(*) AS cnt
       FROM hotspots WHERE is_fallback=0
       GROUP BY day ORDER BY day DESC LIMIT 10"""
).fetchall()
for r in rows:
    print(f"  {r['day']}: {r['cnt']}")

print()
print("=== pub vs fetch diff (sample 5) ===")
rows = conn.execute(
    """SELECT title, published_at, fetched_at,
              (julianday(published_at) - julianday(fetched_at)) * 86400 AS diff_sec
       FROM hotspots WHERE category='ai' AND is_fallback=0
       ORDER BY fetched_at DESC LIMIT 5"""
).fetchall()
for r in rows:
    print(f"  diff={r['diff_sec']:.0f}s  pub={r['published_at'][:19]}  fetch={r['fetched_at'][:19]}")

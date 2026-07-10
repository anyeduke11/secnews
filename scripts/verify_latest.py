"""检查 security/ai 分类最新 items 的 published_at 提取"""
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect("backend/hotspot.db")
conn.row_factory = sqlite3.Row

# Get fetched_at max for each category
print("=== Latest fetched_at by category ===")
for cat in ["ai", "security", "finance", "startup", "bid", "github"]:
    row = conn.execute(
        "SELECT MAX(fetched_at) AS mxf, COUNT(*) AS cnt, "
        "SUM(CASE WHEN published_at != fetched_at THEN 1 ELSE 0 END) AS real_pub "
        "FROM hotspots WHERE category = ?",
        (cat,),
    ).fetchone()
    print(f"  {cat}: max_fetch={row['mxf']}  total={row['cnt']}  real_pub={row['real_pub']}")

# Most recent 5 security items
print()
print("=== Most recent 5 security items ===")
rows = conn.execute(
    """SELECT title, published_at, fetched_at, source, is_fallback,
              substr(url, 1, 60) AS url_short
       FROM hotspots WHERE category = 'security' AND is_fallback = 0
       ORDER BY fetched_at DESC LIMIT 5"""
).fetchall()
for r in rows:
    print(f"  fetch={r['fetched_at'][:19]}  pub={r['published_at'][:19]}")
    print(f"    title={r['title'][:50]}")
    print(f"    url={r['url_short']}")
    print()

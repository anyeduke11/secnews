"""一次性脚本: 检查抓取数据的 published_at 是否真实 (Bug 2 验证)"""
import sqlite3
import sys
from pathlib import Path

db_path = Path("backend/hotspot.db")
if not db_path.exists():
    print(f"DB not found: {db_path}")
    raise SystemExit(1)

# Force UTF-8 stdout (Windows default is GBK, breaks Chinese titles)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

for cat in ["ai", "security", "finance", "startup", "github"]:
    rows = conn.execute(
        """SELECT title, published_at, fetched_at, is_fallback, source,
                  substr(url, 1, 50) AS url_short
           FROM hotspots
           WHERE category = ? AND is_fallback = 0
           ORDER BY published_at DESC LIMIT 2""",
        (cat,),
    ).fetchall()
    print(f"=== {cat} (top 2 by published_at, real data only) ===")
    if not rows:
        print("  (no real data)")
    for r in rows:
        print(f"  title: {r['title'][:60]}")
        print(f"    published_at: {r['published_at']}")
        print(f"    fetched_at:   {r['fetched_at']}")
        print(f"    is_fallback:  {r['is_fallback']}")
        print(f"    source: {r['source']}")
        print(f"    url: {r['url_short']}")
        print()

# Also check the count of real vs fallback by category
print("=== Real vs Fallback counts ===")
for cat in ["ai", "security", "finance", "startup", "bid", "github"]:
    real = conn.execute(
        "SELECT COUNT(*) FROM hotspots WHERE category = ? AND is_fallback = 0",
        (cat,),
    ).fetchone()[0]
    fb = conn.execute(
        "SELECT COUNT(*) FROM hotspots WHERE category = ? AND is_fallback = 1",
        (cat,),
    ).fetchone()[0]
    print(f"  {cat}: real={real}  fallback={fb}  total={real + fb}")

# Time range distribution for AI
print()
print("=== AI published_at distribution (last 5 days) ===")
rows = conn.execute(
    """SELECT date(published_at) AS day, COUNT(*) AS cnt
       FROM hotspots
       WHERE category = 'ai' AND is_fallback = 0
       GROUP BY day
       ORDER BY day DESC
       LIMIT 7"""
).fetchall()
for r in rows:
    print(f"  {r['day']}: {r['cnt']}")

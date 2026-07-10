"""Phase 10 一次性脚本: 补标历史 quality_checked_at"""
import sqlite3
from datetime import datetime, timezone

conn = sqlite3.connect("backend/hotspot.db")
now = datetime.now(timezone.utc).isoformat()
cur = conn.execute(
    "UPDATE hotspots SET quality_checked_at = ? "
    "WHERE quality_checked_at IS NULL OR quality_checked_at = ''",
    (now,),
)
n = cur.rowcount
conn.commit()
print(f"补标 quality_checked_at: {n} 行")
conn.close()

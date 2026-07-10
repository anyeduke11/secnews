"""One-off script: cleanup bad url_check_status='failed' in hotspots table."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "backend" / "hotspot.db"

conn = sqlite3.connect(str(DB_PATH))
cur = conn.execute("SELECT COUNT(*) FROM hotspots WHERE url_check_status = 'failed'")
n = cur.fetchone()[0]
print(f"failed rows: {n}")
if n > 0:
    conn.execute("UPDATE hotspots SET url_check_status = 'skipped' WHERE url_check_status = 'failed'")
    conn.commit()
    print(f"Updated {n} rows to skipped")
conn.close()

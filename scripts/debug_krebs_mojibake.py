"""检查 Krebs 残留实体问题"""
import sqlite3

conn = sqlite3.connect("backend/hotspot.db")
r = conn.execute(
    "SELECT id, title, url FROM hotspots WHERE source = ? AND title LIKE ?",
    ("KrebsOnSecurity", "%Meta%"),
).fetchone()
if r:
    print(f"id={r[0]}")
    print(f"title={r[1]!r}")
    print(f"title bytes (utf-8): {r[1].encode('utf-8')}")
    print(f"title bytes (latin-1 roundtrip): {r[1].encode('latin-1', errors='replace')}")
    # 找残留
    for i, c in enumerate(r[1]):
        if ord(c) > 127 and ord(c) < 256:
            print(f"  pos {i}: char={c!r} ord={ord(c)} hex={ord(c):#x}")

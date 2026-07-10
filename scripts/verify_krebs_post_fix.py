"""Phase 10 验证: Krebs DB 状态最终检查"""
import sqlite3

conn = sqlite3.connect("backend/hotspot.db")
print("=== All Krebs rows (post-final-fix) ===")
for r in conn.execute(
    "SELECT id, title, url FROM hotspots WHERE source = ? ORDER BY id DESC",
    ("KrebsOnSecurity",),
):
    print(f"  {r[1][:80]!r}")
print()
total = conn.execute(
    "SELECT COUNT(*) FROM hotspots WHERE source = ?", ("KrebsOnSecurity",)
).fetchone()[0]
print(f"Total: {total}")

# Residual lowercase-starting titles
n_low = conn.execute(
    "SELECT COUNT(*) FROM hotspots WHERE source = 'KrebsOnSecurity' "
    "AND title GLOB '[a-z]*'"
).fetchone()[0]
print(f"Still lowercase start: {n_low}")

# Specific item: user-reported CISA article
print("\n=== User-reported CISA article ===")
for r in conn.execute(
    "SELECT id, title, url FROM hotspots "
    "WHERE url LIKE '%cisa-admin-leaked-aws-govcloud-keys%' "
    "OR title LIKE '%CISA Admin Leaked%'"
):
    print(f"  id={r[0]}")
    print(f"  title={r[1]!r}")
    print(f"  url={r[2]}")

"""Phase 10 验证: 残留小写开头 Krebs 行"""
import sqlite3

conn = sqlite3.connect("backend/hotspot.db")
print("=== lowercase-start Krebs rows ===")
for r in conn.execute(
    "SELECT id, title, url FROM hotspots WHERE source = ?",
    ("KrebsOnSecurity",),
):
    t = (r[1] or "").strip()
    if not t:
        continue
    # 启发式: 以小写字母开头(说明是 body 片段) 或 含 " a letter" / "a breach" 特征
    if t[0].islower() or " a letter" in t.lower() or "a breach" in t.lower():
        print(f"  id={r[0]}")
        print(f"    title={t[:100]!r}")
        print(f"    url={r[2][:120]}")
        print()

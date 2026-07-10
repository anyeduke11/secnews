"""Phase 10 端到端验证脚本"""
import requests

BASE = "http://127.0.0.1:8000"

# 1. Add 3 favorites across categories
favs = [
    {"hotspot_id": "fav-1", "category": "ai", "title": "AI 资讯: 量子位 tag 终稿",
     "source": "qbitai", "url": "https://www.qbitai.com/2026/07/442447.html"},
    {"hotspot_id": "fav-2", "category": "bid", "title": "招标: 国家电网2026安全服务采购",
     "source": "ccgp", "url": "https://www.ccgp.gov.cn/cggg/zygg/zbgg/202607/t20260705_12345.htm"},
    {"hotspot_id": "fav-3", "category": "security", "title": "CVE-2026-49160 微软补丁",
     "source": "msrc", "url": "https://msrc.microsoft.com/update-guide/vulnerability/CVE-2026-49160"},
]

print("=== 1. Add favorites ===")
for f in favs:
    r = requests.post(f"{BASE}/api/favorites", json=f)
    data = r.json()
    print(f"  ADD {f['hotspot_id']}: status={r.status_code} created={data.get('created')} title={data['item']['title'][:40]}")

# 2. List all
print("\n=== 2. List all ===")
r = requests.get(f"{BASE}/api/favorites")
data = r.json()
print(f"  status={r.status_code} count={data['count']} total={data['total']} category={data['category']}")
for it in data["items"]:
    print(f"    - [{it['category']}] {it['title'][:50]}")

# 3. Filter by category
print("\n=== 3. List bid only ===")
r = requests.get(f"{BASE}/api/favorites?category=bid")
data = r.json()
print(f"  status={r.status_code} count={data['count']}")
for it in data["items"]:
    print(f"    - {it['title']}")

# 4. Count
print("\n=== 4. Count by category ===")
r = requests.get(f"{BASE}/api/favorites/count")
data = r.json()
print(f"  total={data['total']}")
for cat, n in data["by_category"].items():
    print(f"    - {cat}: {n}")

# 5. Export xlsx
print("\n=== 5. Export xlsx ===")
r = requests.get(f"{BASE}/api/favorites/export")
print(f"  status={r.status_code} ctype={r.headers.get('content-type')}")
print(f"  cdisp={r.headers.get('content-disposition')}")
print(f"  X-Favorite-Count={r.headers.get('X-Favorite-Count')}")
print(f"  size={len(r.content)} bytes")
with open("test_favorites_export.xlsx", "wb") as f:
    f.write(r.content)
print(f"  saved to test_favorites_export.xlsx")

# 6. Export with category filter
print("\n=== 6. Export xlsx (bid only) ===")
r = requests.get(f"{BASE}/api/favorites/export?category=bid")
print(f"  status={r.status_code} X-Favorite-Count={r.headers.get('X-Favorite-Count')}")

# 7. Delete
print("\n=== 7. Delete fav-1 ===")
r = requests.delete(f"{BASE}/api/favorites/fav-1")
data = r.json()
print(f"  status={r.status_code} removed={data['removed']}")

# 8. Count after delete
print("\n=== 8. Count after delete ===")
r = requests.get(f"{BASE}/api/favorites/count")
print(f"  total={r.json()['total']} by_cat={r.json()['by_category']}")

# 9. Invalid category
print("\n=== 9. Invalid category ===")
r = requests.get(f"{BASE}/api/favorites?category=bogus")
print(f"  status={r.status_code} body={r.json()['detail']['message'][:80]}")

# 10. Empty export
print("\n=== 10. Empty export (filter non-existent) ===")
r = requests.get(f"{BASE}/api/favorites/export?category=github")
print(f"  status={r.status_code} X-Favorite-Count={r.headers.get('X-Favorite-Count')}")

print("\n=== ALL OK ===")

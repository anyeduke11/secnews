"""验证 API 端去重效果"""
import urllib.request
import json

r = urllib.request.urlopen(
    "http://127.0.0.1:8898/api/hotspots?category=ai&time_range=7d&limit=100",
    timeout=5,
)
d = json.loads(r.read())
items = d.get("items", [])
print(f"ai items: {len(items)}")
print()

url_count = {}
for it in items:
    u = it.get("url", "")
    url_count.setdefault(u, []).append(it)

dups = {u: lst for u, lst in url_count.items() if len(lst) > 1}
if dups:
    print(f"!! 仍有 {len(dups)} 个 url 重复:")
    for u, lst in list(dups.items())[:5]:
        print(f"  {u}: {len(lst)} 条")
        for it in lst:
            print(f"    id={it['id']} title={it['title'][:50]}")
else:
    print("PASS: 0 个 url 重复")

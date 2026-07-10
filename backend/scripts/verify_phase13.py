"""Phase 13 验证脚本:检查 /api/hotspots 是否还有 fallback URL。"""
import urllib.request
import json

r = urllib.request.urlopen("http://127.0.0.1:8000/api/hotspots?limit=20&category=bid")
d = json.loads(r.read())
items = d.get("items", [])
print(f"bid 分类返回 {len(items)} 条")
bad = [
    it for it in items
    if "example.com" in str(it.get("url", ""))
    or "google.com/search" in str(it.get("url", ""))
    or "bing.com/search" in str(it.get("url", ""))
]
print(f"含 example.com / google.com / bing.com 的: {len(bad)}")
for it in items[:5]:
    print("---")
    print("  title:", it.get("title", "")[:50])
    print("  url:", it.get("url", "")[:80])
    print("  is_fallback:", it.get("is_fallback", "?"))
    print("  source:", it.get("source", "?"))

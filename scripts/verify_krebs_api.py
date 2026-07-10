"""验证 API 返回的 Krebs 标题是否正确(通过 JSON 解析)"""
import json
import urllib.request

r = urllib.request.urlopen("http://127.0.0.1:8000/api/hotspots?category=security&limit=30", timeout=10)
data = json.loads(r.read().decode("utf-8"))
krebs = [it for it in data["items"] if it["source"] == "KrebsOnSecurity"]
print(f"Krebs count: {len(krebs)}")
for it in krebs:
    print(f"  title: {it['title']}")
    print(f"    url: {it['url']}")
print()
# Sanity: 标题正确性
correct = "CISA Admin Leaked AWS GovCloud Keys on Github" in [it["title"] for it in krebs]
no_comments = not any("comments" in it["title"].lower() for it in krebs)
no_permalink = not any(it["title"].lower().startswith("permalink to ") for it in krebs)
no_anchor = not any("#comments" in it["url"] for it in krebs)
no_lowercase_start = not any(it["title"] and it["title"][0].islower() and "a letter" not in it["title"].lower() for it in krebs)
print(f"=== Sanity checks ===")
print(f"  CISA title present: {correct}")
print(f"  No 'comments' in title: {no_comments}")
print(f"  No 'Permalink to' in title: {no_permalink}")
print(f"  No '#comments' in url: {no_anchor}")
print(f"  No lowercase-start fragments: {no_lowercase_start}")

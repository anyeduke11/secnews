"""直接调用 _parse_html 看新代码能否从 Krebs URL 提取时间"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.collectors.security_collector import SecurityCollector
from datetime import datetime, timezone
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

c = SecurityCollector()
# 找 Krebs 源
for s in c.sources:
    if "krebs" in s.get("name", "").lower() or "krebsonsecurity" in s.get("url", "").lower():
        print(f"Found source: {s['name']} -> {s['url']}")
        # 测试 URL 提取
        from backend.collectors.base import _extract_published_at
        # qbitai 风格 URL
        test_url = "https://krebsonsecurity.com/2026/06/scattered-spider-hackers"
        dt = _extract_published_at("", test_url)
        print(f"  _extract_published_at({test_url!r}) = {dt}")

        # 实际 HTML
        test_html = """<html><body>
<h2 class="entry-title">
  <a href="https://krebsonsecurity.com/2026/06/scattered-spider-hackers" rel="bookmark">Test Article With Sufficient Length</a>
</h2>
</body></html>"""
        raw = c._parse_html(test_html, s)
        print(f"  _parse_html returned {len(raw)} items")
        for r in raw:
            print(f"    title={r['title']}")
            print(f"    url={r['url']}")
            print(f"    published_at={r.get('published_at')}")
        break
else:
    print("No Krebs source found")
    for s in c.sources[:5]:
        print(f"  {s['name']}: {s['url']}")

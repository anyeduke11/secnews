"""Phase 10 调试: 用 base.py 默认 _parse_html 跑 krebsonsecurity.com"""
import re
import ssl
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.collectors.base import BaseCollector

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
req = urllib.request.Request("https://krebsonsecurity.com/", headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=20, context=ctx).read().decode("utf-8", errors="ignore")
print(f"HTML length: {len(html)}\n")


class _T(BaseCollector):
    category = None  # type: ignore
    sources = [{"name": "KrebsOnSecurity", "url": "https://krebsonsecurity.com/", "score": 85}]

    def _fallback(self):
        return []

    def fetch_source(self, source):
        return self._parse_html(html, source), None  # type: ignore


t = _T()
items = t._parse_html(html, t.sources[0])  # type: ignore
print(f"Default parser extracted {len(items)} items:")
for i, it in enumerate(items[:15]):
    print(f"  {i+1}. title={it['title'][:80]!r}")
    print(f"      url={it['url'][:100]}")

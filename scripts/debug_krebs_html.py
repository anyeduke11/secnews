"""Phase 10 调试脚本: 检查 krebsonsecurity.com HTML 结构"""
import re
import ssl
import urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
req = urllib.request.Request("https://krebsonsecurity.com/", headers={"User-Agent": "Mozilla/5.0"})
try:
    html = urllib.request.urlopen(req, timeout=20, context=ctx).read().decode("utf-8", errors="ignore")
    print(f"HTML length: {len(html)}")

    # 抓 h1.entry-title
    print("\n=== h1.entry-title ===")
    for m in re.findall(r'<h1[^>]*class="entry-title"[^>]*>(.*?)</h1>', html, re.S)[:5]:
        text = re.sub(r"<[^>]+>", "", m).strip()
        print(f"  '{text[:120]}'")

    # 抓 h2.entry-title
    print("\n=== h2.entry-title ===")
    for m in re.findall(r'<h2[^>]*class="entry-title"[^>]*>(.*?)</h2>', html, re.S)[:5]:
        text = re.sub(r"<[^>]+>", "", m).strip()
        print(f"  '{text[:120]}'")

    # 抓 99 comments 上下文
    print("\n=== 99 comments context ===")
    for m in re.finditer(r'.{0,100}(\d+)\s*comments.{0,100}', html, re.I):
        print(f"  ...{m.group(0)[:200]}...")
        if len([1 for _ in re.finditer(r'.{0,100}(\d+)\s*comments.{0,100}', html, re.I)]) > 3:
            break

    # 抓文章 article 标签 + 链接
    print("\n=== article tag ===")
    for m in re.findall(r'<article[^>]*>(.{0,500})', html, re.S)[:2]:
        text = re.sub(r"<[^>]+>", " ", m).strip()[:200]
        print(f"  '{text}'")

    # 抓 entry-title 链接
    print("\n=== entry-title <a> links ===")
    for m in re.findall(r'<a[^>]+href="([^"]+)"[^>]*rel="bookmark"[^>]*>([^<]+)</a>', html, re.S)[:5]:
        print(f"  URL: {m[0][:90]}")
        print(f"  TITLE: {m[1].strip()[:120]}")

    # 抓第一条文章 entry-title 完整上下文
    print("\n=== First entry-title + surrounding context ===")
    m = re.search(r'<h[12][^>]*class="entry-title"[^>]*>(.{0,400})', html, re.S)
    if m:
        print(f"  CONTEXT: {m.group(0)[:500]}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")

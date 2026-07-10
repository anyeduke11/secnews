"""Phase 9 端到端验证:通过前端 8898 代理测试所有 API。"""
import urllib.request
import json

BASE = "http://127.0.0.1:8898"

PATHS = [
    "/api/health",
    "/api/stats",
    "/api/quality/rules",
    "/api/quality/summary",
    "/api/quality/source-reputation",
    "/api/categories",
    "/api/trends",
    "/api/hotspots?limit=5",
    "/api/hotspots?category=ai&limit=10",
    "/api/hotspots?keyword=test&limit=5",
]

print(f"通过前端代理 {BASE} 测试所有 API 端点")
print("=" * 60)

all_ok = True
for path in PATHS:
    try:
        r = urllib.request.urlopen(f"{BASE}{path}", timeout=5)
        body = r.read()
        d = json.loads(body) if body else {}
        if path == "/api/health":
            db = d.get("components", {}).get("db", {})
            print(f"  OK {r.status} {path}: status={d.get('status')} hotspots={db.get('hotspots_count')}")
        elif path == "/api/quality/rules":
            print(f"  OK {r.status} {path}: rules={len(d.get('rules', []))}")
        elif path == "/api/stats":
            print(f"  OK {r.status} {path}: total={d.get('db', {}).get('hotspots_total')}")
        elif path == "/api/categories":
            print(f"  OK {r.status} {path}: cats={len(d.get('categories', []))}")
        elif path.startswith("/api/hotspots"):
            print(f"  OK {r.status} {path}: items={len(d.get('items', []))}")
        else:
            print(f"  OK {r.status} {path}: bytes={len(body)}")
    except Exception as e:
        all_ok = False
        print(f"  ERR {path}: {type(e).__name__}: {str(e)[:100]}")

print("=" * 60)
if all_ok:
    print("ALL PASS: 500 错误已消除,所有 API 通过前端代理正常返回")
else:
    print("FAIL: 部分端点仍有问题")

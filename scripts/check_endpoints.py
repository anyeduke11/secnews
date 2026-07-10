"""Phase 9 端点健康检查。"""
import urllib.request
import json

PATHS = [
    "/api/health",
    "/api/stats",
    "/api/quality/rules",
    "/api/quality/summary",
    "/api/quality/source-reputation",
    "/api/categories",
    "/api/trends",
    "/api/export",
    "/api/hotspots?limit=5",
]

for path in PATHS:
    try:
        r = urllib.request.urlopen(f"http://127.0.0.1:8000{path}", timeout=5)
        body = r.read()
        d = json.loads(body) if body else {}
        if path == "/api/health":
            db = d.get("components", {}).get("db", {})
            print(f"{path}: status={d.get('status')} hotspots={db.get('hotspots_count')}")
        elif path == "/api/quality/rules":
            print(f"{path}: rules_count={len(d.get('rules', []))}")
        elif path == "/api/stats":
            print(f"{path}: hotspots_total={d.get('db', {}).get('hotspots_total')} runs_24h={d.get('collect_runs_24h')}")
        elif path == "/api/categories":
            print(f"{path}: cats={len(d.get('categories', []))}")
        elif path == "/api/hotspots":
            print(f"{path}: items={len(d.get('items', []))} total={d.get('total')}")
        else:
            print(f"{path}: OK bytes={len(body)}")
    except Exception as e:
        print(f"{path}: ERR {type(e).__name__}: {e}")

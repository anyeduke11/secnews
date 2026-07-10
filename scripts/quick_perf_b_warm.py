"""Scenario B with warmup: warm cache, then measure mixed QPS.

Phase 8: 通过 PERF_BASE_URL 环境变量支持自定义后端地址。
"""
import os
import time
import random
import requests
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.getenv("PERF_BASE_URL", "http://127.0.0.1:8000")
N = int(os.getenv("PERF_N", "200"))

ENDPOINTS = [
    ("/api/hotspots?category=ai", 0.4),
    ("/api/hotspots?category=security", 0.4),
    ("/api/trends?hours=24", 0.3),
    ("/api/categories", 0.2),
    ("/api/health", 0.1),
]


def pick():
    r = random.random()
    cum = 0
    for path, w in ENDPOINTS:
        cum += w
        if r < cum:
            return path
    return ENDPOINTS[-1][0]


def hit(path):
    t0 = time.time()
    try:
        r = requests.get(BASE + path, timeout=10)
        dt = (time.time() - t0) * 1000
        return dt, r.status_code
    except Exception as e:
        dt = (time.time() - t0) * 1000
        return dt, -1


# Warmup: 3 rounds of all endpoints
print("[warmup] 3 rounds of all endpoints")
for round_n in range(3):
    for path, _ in ENDPOINTS:
        requests.get(BASE + path, timeout=10)
    time.sleep(0.5)

print(f"[measure] starting test")
t_start = time.time()
with ThreadPoolExecutor(max_workers=20) as ex:
    futures = [ex.submit(hit, pick()) for _ in range(N)]
    results = []
    for f in as_completed(futures, timeout=120):
        try:
            results.append(f.result())
        except Exception:
            pass

duration = time.time() - t_start
latencies = sorted([r[0] for r in results])
statuses = {}
for _, sc in results:
    statuses[sc] = statuses.get(sc, 0) + 1
errs = sum(1 for _, sc in results if sc != 200)

def pct(p):
    idx = int(len(latencies) * p / 100)
    return latencies[min(idx, len(latencies) - 1)]


print(f"Total: {N}, Duration: {duration:.2f}s, QPS: {N / duration:.1f}")
print(f"Status codes: {statuses}")
print(f"Errors: {errs} ({errs * 100 / N:.2f}%)")
print(f"Latency avg: {statistics.mean(latencies):.2f}ms")
print(f"Latency p50: {pct(50):.2f}ms")
print(f"Latency p95: {pct(95):.2f}ms")
print(f"Latency p99: {pct(99):.2f}ms")
print(f"Latency max: {max(latencies):.2f}ms")

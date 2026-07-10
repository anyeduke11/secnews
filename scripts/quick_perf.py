"""Quick perf test: hit /api/hotspots 100 times, measure latency.

Phase 8: 通过 PERF_BASE_URL 环境变量支持自定义后端地址。
"""
import os
import time
import requests
import statistics

URL = os.getenv("PERF_BASE_URL", "http://127.0.0.1:8000") + "/api/hotspots?category=ai"
N = int(os.getenv("PERF_N", "200"))

latencies = []
errors = 0
statuses = {}

t_start = time.time()
for i in range(N):
    try:
        t0 = time.time()
        r = requests.get(URL, timeout=10)
        dt = (time.time() - t0) * 1000
        latencies.append(dt)
        sc = r.status_code
        statuses[sc] = statuses.get(sc, 0) + 1
        if sc >= 500:
            errors += 1
    except Exception as e:
        errors += 1
        statuses["exception"] = statuses.get("exception", 0) + 1

duration = time.time() - t_start

latencies.sort()
def pct(p):
    idx = int(len(latencies) * p / 100)
    return latencies[min(idx, len(latencies) - 1)]

print(f"Total: {N}, Duration: {duration:.2f}s, QPS: {N / duration:.1f}")
print(f"Status codes: {statuses}")
print(f"Errors (5xx): {errors}")
print(f"Latency avg: {statistics.mean(latencies):.2f}ms")
print(f"Latency p50: {pct(50):.2f}ms")
print(f"Latency p95: {pct(95):.2f}ms")
print(f"Latency p99: {pct(99):.2f}ms")
print(f"Latency max: {max(latencies):.2f}ms")

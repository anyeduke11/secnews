"""Quick perf test: hit /api/hotspots N times, measure latency.

Phase 8: 通过 PERF_BASE_URL 环境变量支持自定义后端地址。
v0.5 T0: 新增 --cold 双轨冷路径模式：
  - 每 K 个请求前调用 POST /api/cache/clear 清空进程内缓存
  - 随机化 category × time_range，使 list_cache key 不重复命中
  旧基线（同一 URL 打 N 次）第 2 次起全命中缓存，测的是缓存不是查询；
  冷路径才是 Task 1（列表索引化）优化的真实对象。

用法:
  .venv/bin/python scripts/quick_perf.py            # 热路径（原语义）
  .venv/bin/python scripts/quick_perf.py --cold     # 冷路径（v0.5 验收口径）
"""
import argparse
import os
import random
import statistics
import time

import requests

BASE = os.getenv("PERF_BASE_URL", "http://127.0.0.1:8000")
N = int(os.getenv("PERF_N", "200"))

CATEGORIES = ["ai", "security", "bid", "vuln", "company", "policy", "tech", "finance"]
TIME_RANGES = ["1d", "7d", "30d"]
COLD_CLEAR_EVERY = 10  # 每 10 个请求清一次缓存，保证全程走 DB


def build_url(cold: bool) -> str:
    if not cold:
        return BASE + "/api/hotspots?category=ai"
    cat = random.choice(CATEGORIES)
    tr = random.choice(TIME_RANGES)
    return f"{BASE}/api/hotspots?category={cat}&time_range={tr}"


def clear_cache() -> None:
    try:
        requests.post(BASE + "/api/cache/clear", timeout=5)
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="hotspots API perf probe")
    parser.add_argument("--cold", action="store_true",
                        help="冷路径：随机 category/time_range + 周期性清缓存")
    args = parser.parse_args()

    mode = "cold" if args.cold else "warm"
    latencies = []
    errors = 0
    statuses = {}

    t_start = time.time()
    for i in range(N):
        if args.cold and i % COLD_CLEAR_EVERY == 0:
            clear_cache()
        try:
            t0 = time.time()
            r = requests.get(build_url(args.cold), timeout=10)
            dt = (time.time() - t0) * 1000
            latencies.append(dt)
            sc = r.status_code
            statuses[sc] = statuses.get(sc, 0) + 1
            if sc >= 500:
                errors += 1
        except Exception:
            errors += 1
            statuses["exception"] = statuses.get("exception", 0) + 1

    duration = time.time() - t_start

    latencies.sort()

    def pct(p):
        idx = int(len(latencies) * p / 100)
        return latencies[min(idx, len(latencies) - 1)]

    print(f"Mode: {mode}")
    print(f"Total: {N}, Duration: {duration:.2f}s, QPS: {N / duration:.1f}")
    print(f"Status codes: {statuses}")
    print(f"Errors (5xx): {errors}")
    if latencies:
        print(f"Latency avg: {statistics.mean(latencies):.2f}ms")
        print(f"Latency p50: {pct(50):.2f}ms")
        print(f"Latency p95: {pct(95):.2f}ms")
        print(f"Latency p99: {pct(99):.2f}ms")
        print(f"Latency max: {max(latencies):.2f}ms")


if __name__ == "__main__":
    main()

"""Phase 9 验证脚本:触发 collect 期间持续请求 /api/hotspots,确认不再超时。

预期行为(asyncio.to_thread 修复后):
- collect 期间所有 /api/hotspots 请求都能在 5s 内返回
- 没有任何请求超过 5s timeout
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "http://127.0.0.1:8000/api/hotspots?limit=10"
TIMEOUT = 5.0  # 与前端 useHotspotData.ts 一致


def fetch_once(idx: int) -> tuple[int, float, str]:
    """返回 (idx, elapsed, status_or_error)."""
    t0 = time.perf_counter()
    try:
        r = urllib.request.urlopen(API, timeout=TIMEOUT)
        elapsed = time.perf_counter() - t0
        body = r.read()
        ok = len(body) > 0
        return idx, elapsed, f"OK {r.status} bytes={len(body)}"
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return idx, elapsed, f"ERR {type(e).__name__}: {e}"


async def continuous_requests(duration_s: float) -> list[tuple[int, float, str]]:
    """在 duration_s 内持续并发请求 /api/hotspots。"""
    results: list[tuple[int, float, str]] = []
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=4)
    end = time.perf_counter() + duration_s
    idx = 0
    while time.perf_counter() < end:
        # 4 路并发
        tasks = [
            loop.run_in_executor(executor, fetch_once, idx + i)
            for i in range(4)
        ]
        done = await asyncio.gather(*tasks)
        results.extend(done)
        idx += 4
    executor.shutdown(wait=True)
    return results


async def main():
    # 1) 先持续请求 5s 作为 baseline
    print("[1] baseline 5s continuous requests...")
    baseline = await continuous_requests(5.0)
    print(f"    {len(baseline)} requests, "
          f"latency min/avg/max = "
          f"{min(r[1] for r in baseline):.3f}/"
          f"{sum(r[1] for r in baseline)/len(baseline):.3f}/"
          f"{max(r[1] for r in baseline):.3f}s")

    # 2) 触发 collect_all_job + 持续请求 30s
    print("[2] trigger collect + continuous 30s requests...")
    from backend.services.collection_service import CollectionService
    svc = CollectionService()

    # 启动 collect (后台任务)
    collect_task = asyncio.create_task(svc.run_once())

    # 同时持续请求 30s
    during = await continuous_requests(30.0)

    # 等 collect 完成
    try:
        await asyncio.wait_for(collect_task, timeout=60)
        collect_status = "DONE"
    except asyncio.TimeoutError:
        collect_status = "TIMEOUT"
    except Exception as e:
        collect_status = f"ERR {type(e).__name__}: {e}"

    print(f"    collect: {collect_status}")
    print(f"    {len(during)} requests during collect, "
          f"latency min/avg/max = "
          f"{min(r[1] for r in during):.3f}/"
          f"{sum(r[1] for r in during)/len(during):.3f}/"
          f"{max(r[1] for r in during):.3f}s")

    # 3) 结果分析
    slow = [r for r in during if r[1] >= TIMEOUT]
    errors = [r for r in during if r[2].startswith("ERR")]
    print()
    print("=" * 60)
    if not slow and not errors:
        print(f"PASS: 0 slow requests (>= {TIMEOUT}s), 0 errors")
        print(f"      max latency {max(r[1] for r in during):.3f}s during collect")
        print("      Phase 9 asyncio.to_thread 修复有效")
    else:
        print(f"FAIL: {len(slow)} slow, {len(errors)} errors")
        for r in slow[:5]:
            print(f"  slow #{r[0]}: {r[1]:.3f}s {r[2]}")
        for r in errors[:5]:
            print(f"  err  #{r[0]}: {r[1]:.3f}s {r[2]}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

"""场景 A — 单接口 100 QPS 压测 — Phase 7 Task 3.2.

默认 60s 内对 ``GET /api/hotspots?category=ai`` 发起 ~6000 次请求
（ThreadPoolExecutor 100 worker），记录每条 status / duration_ms。

结果：
- 控制台打印汇总（total / error / avg / p50 / p95 / p99 / max）
- 原始数据写入 ``scripts/logs/loadtest_A_<ts>.jsonl``

环境变量
--------
- ``LOADTEST_DURATION_S`` 测试时长 (秒, 默认 60)
- ``LOADTEST_WORKERS``    并发 worker 数 (默认 100)
- ``LOADTEST_BASE_URL``   后端 base URL (默认 http://127.0.0.1:8000)
- ``LOADTEST_CATEGORY``   测试分类 (默认 ``ai``)
- ``LOADTEST_QPS``        目标 QPS (默认 100, 仅作限速上限)

用法
----
    $ python scripts/loadtest/single_endpoint.py
    $ LOADTEST_DURATION_S=10 LOADTEST_WORKERS=20 python scripts/loadtest/single_endpoint.py
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOGS_DIR = SCRIPT_DIR.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
def _http_get(url: str, timeout: float = 10.0) -> tuple[int, float, str]:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "loadtest-A/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(1024)
            return r.status, round((time.time() - t0) * 1000, 2), ""
    except urllib.error.HTTPError as e:
        return e.code, round((time.time() - t0) * 1000, 2), f"HTTP {e.code}"
    except Exception as e:
        return 0, round((time.time() - t0) * 1000, 2), f"{type(e).__name__}: {str(e)[:80]}"


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(int(len(s) * p), len(s) - 1)
    return round(s[idx], 2)


def main() -> int:
    duration_s = int(os.getenv("LOADTEST_DURATION_S", "60"))
    workers = int(os.getenv("LOADTEST_WORKERS", "100"))
    base_url = os.getenv("LOADTEST_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    category = os.getenv("LOADTEST_CATEGORY", "ai")
    target_qps = int(os.getenv("LOADTEST_QPS", "100"))

    url = f"{base_url}/api/hotspots?category={category}"
    print(
        f"[loadtest_A] url={url} duration={duration_s}s workers={workers} "
        f"target_qps={target_qps}",
        flush=True,
    )

    # 预检：后端可达
    try:
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=5) as r:
            if r.status != 200:
                print(f"[loadtest_A] backend not healthy, exit", flush=True)
                return 1
    except Exception as e:
        print(f"[loadtest_A] cannot reach backend: {e}", flush=True)
        return 1

    stop_flag = {"stop": False}

    def _on_signal(_sig, _frm):
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    out_path = LOGS_DIR / f"loadtest_A_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    f_out = open(out_path, "w", encoding="utf-8", buffering=1)

    samples: list[tuple[float, int, float, str]] = []  # (ts, status, dur, err)
    start = time.time()
    deadline = start + duration_s
    inflight = 0

    def _one() -> tuple[int, float, str]:
        return _http_get(url)

    # 节流：目标 QPS
    interval = 1.0 / target_qps if target_qps > 0 else 0.0
    next_dispatch = start

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            dispatch_log = 0
            while not stop_flag["stop"] and time.time() < deadline:
                now = time.time()
                # 一次最多 dispatch 一批，保持并发
                batch: list = []
                # 在本 1ms 内尽量多发，直到 inflight == workers
                while inflight < workers and time.time() < deadline and not stop_flag["stop"]:
                    if interval > 0 and time.time() < next_dispatch:
                        time.sleep(max(0, next_dispatch - time.time()))
                    next_dispatch = time.time() + interval
                    fut = pool.submit(_one)
                    fut._t_submit = time.time()  # type: ignore[attr-defined]
                    batch.append(fut)
                    dispatch_log += 1

                # 回收已完成的
                if not batch:
                    time.sleep(0.001)
                    continue
                for fut in as_completed(batch, timeout=0.05):
                    try:
                        status, dur, err = fut.result()
                        samples.append((time.time(), status, dur, err))
                        f_out.write(
                            json.dumps(
                                {
                                    "ts": datetime.utcnow().isoformat() + "Z",
                                    "status": status,
                                    "duration_ms": dur,
                                    "error": err,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                    except Exception as e:
                        samples.append((time.time(), 0, 0.0, str(e)[:80]))
    finally:
        f_out.close()

    duration = time.time() - start
    if not samples:
        print("[loadtest_A] no samples collected", flush=True)
        return 1

    statuses = [s[1] for s in samples]
    durations = [s[2] for s in samples]
    succ = sum(1 for st in statuses if 200 <= st < 300)
    err5xx = sum(1 for st in statuses if 500 <= st < 600)
    err_other = sum(1 for st in statuses if not (200 <= st < 300) and st != 0)
    err_net = sum(1 for st in statuses if st == 0)
    qps_actual = round(len(samples) / duration, 2) if duration > 0 else 0.0

    summary = {
        "scenario": "A_single_endpoint",
        "url": url,
        "duration_s": round(duration, 2),
        "total": len(samples),
        "success": succ,
        "error_5xx": err5xx,
        "error_other_http": err_other,
        "error_network": err_net,
        "error_count": len(samples) - succ,
        "qps_actual": qps_actual,
        "latency_ms": {
            "avg": round(sum(durations) / len(durations), 2),
            "p50": _percentile(durations, 0.50),
            "p95": _percentile(durations, 0.95),
            "p99": _percentile(durations, 0.99),
            "max": max(durations) if durations else 0.0,
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    summary_path = out_path.with_suffix(".summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[loadtest_A] raw={out_path} summary={summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

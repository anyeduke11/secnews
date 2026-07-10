"""场景 B — 混合 500 QPS 压测 — Phase 7 Task 3.5.

4 个端点按 4:3:2:1 权重混合：
- hotspots (40%):  ``/api/hotspots?category={cycle}``
- trends   (30%):  ``/api/trends?hours=24``
- categories (20%): ``/api/categories``
- health   (10%):  ``/api/health``

ThreadPoolExecutor(max_workers=100) 节流发到目标 QPS。

环境变量
--------
- ``LOADTEST_DURATION_S`` 默认 60
- ``LOADTEST_WORKERS``    默认 100
- ``LOADTEST_QPS``        默认 500
- ``LOADTEST_BASE_URL``   默认 http://127.0.0.1:8000

结果写入 ``scripts/logs/loadtest_B_<ts>.jsonl`` 和 ``.summary.json``。
"""
from __future__ import annotations

import json
import os
import random
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

CATEGORIES = ["ai", "security", "finance", "startup", "bid", "github", "all"]


# ---------------------------------------------------------------------------
# 端点定义
# ---------------------------------------------------------------------------
def _endpoint_hotspots(_base: str) -> str:
    cat = CATEGORIES[int(time.time() // 10) % len(CATEGORIES)]
    return f"/api/hotspots?category={cat}"


ENDPOINTS = [
    ("hotspots", 4, lambda base: f"/api/hotspots?category={_pick_category()}"),
    ("trends", 3, lambda base: "/api/trends?hours=24"),
    ("categories", 2, lambda base: "/api/categories"),
    ("health", 1, lambda base: "/api/health"),
]
WEIGHT_SUM = sum(w for _, w, _ in ENDPOINTS)


def _pick_category() -> str:
    # 让分类随时间循环，保证均匀覆盖
    return CATEGORIES[int(time.time() // 5) % len(CATEGORIES)]


def _pick_endpoint() -> tuple[str, str]:
    """按权重选端点，返回 (name, path)。"""
    r = random.random() * WEIGHT_SUM
    acc = 0.0
    for name, w, fn in ENDPOINTS:
        acc += w
        if r <= acc:
            return name, fn("")
    return ENDPOINTS[-1][0], ENDPOINTS[-1][2]("")


# ---------------------------------------------------------------------------
def _http_get(url: str, timeout: float = 10.0) -> tuple[int, float, str]:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "loadtest-B/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(2048)
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
    target_qps = int(os.getenv("LOADTEST_QPS", "500"))
    base_url = os.getenv("LOADTEST_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

    print(
        f"[loadtest_B] base={base_url} duration={duration_s}s workers={workers} "
        f"target_qps={target_qps}",
        flush=True,
    )

    # 预检
    try:
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=5) as r:
            if r.status != 200:
                print("[loadtest_B] backend not healthy, exit", flush=True)
                return 1
    except Exception as e:
        print(f"[loadtest_B] cannot reach backend: {e}", flush=True)
        return 1

    stop_flag = {"stop": False}

    def _on_signal(_sig, _frm):
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    out_path = LOGS_DIR / f"loadtest_B_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    f_out = open(out_path, "w", encoding="utf-8", buffering=1)

    samples: list[tuple[float, str, int, float, str]] = []  # ts, ep, st, dur, err
    start = time.time()
    deadline = start + duration_s
    interval = 1.0 / target_qps if target_qps > 0 else 0.0
    next_dispatch = start
    ep_counter: dict[str, int] = {name: 0 for name, _, _ in ENDPOINTS}

    def _one(ep_name: str, ep_path: str) -> tuple[str, int, float, str]:
        return ep_name, *_http_get(f"{base_url}{ep_path}")

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            batch: list = []
            while not stop_flag["stop"] and time.time() < deadline:
                # 维持并发
                while len(batch) < workers and time.time() < deadline and not stop_flag["stop"]:
                    if interval > 0 and time.time() < next_dispatch:
                        time.sleep(max(0, next_dispatch - time.time()))
                    next_dispatch = time.time() + interval
                    ep_name, ep_path = _pick_endpoint()
                    fut = pool.submit(_one, ep_name, ep_path)
                    batch.append(fut)
                # 回收
                if not batch:
                    time.sleep(0.001)
                    continue
                done = []
                for fut in as_completed(batch, timeout=0.05):
                    try:
                        ep_name, st, dur, err = fut.result()
                    except Exception as e:
                        ep_name, st, dur, err = "?", 0, 0.0, str(e)[:80]
                    samples.append((time.time(), ep_name, st, dur, err))
                    ep_counter[ep_name] = ep_counter.get(ep_name, 0) + 1
                    f_out.write(
                        json.dumps(
                            {
                                "ts": datetime.utcnow().isoformat() + "Z",
                                "endpoint": ep_name,
                                "status": st,
                                "duration_ms": dur,
                                "error": err,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    done.append(fut)
                for d in done:
                    batch.remove(d)
    finally:
        f_out.close()

    duration = time.time() - start
    if not samples:
        print("[loadtest_B] no samples", flush=True)
        return 1

    statuses = [s[2] for s in samples]
    succ = sum(1 for st in statuses if 200 <= st < 300)
    err5xx = sum(1 for st in statuses if 500 <= st < 600)
    durations = [s[3] for s in samples if s[2] > 0]
    qps_actual = round(len(samples) / duration, 2) if duration > 0 else 0.0

    # 按 endpoint 分组
    by_ep: dict[str, list[tuple[int, float]]] = {}
    for _ts, ep, st, dur, _err in samples:
        by_ep.setdefault(ep, []).append((st, dur))

    ep_stats = {}
    for ep, items in by_ep.items():
        sts = [x[0] for x in items]
        durs = [x[1] for x in items if x[0] > 0]
        ep_stats[ep] = {
            "count": len(items),
            "success_rate": round(sum(1 for s in sts if 200 <= s < 300) / len(sts), 4),
            "latency_ms": {
                "avg": round(sum(durs) / len(durs), 2) if durs else 0.0,
                "p50": _percentile(durs, 0.50),
                "p95": _percentile(durs, 0.95),
                "p99": _percentile(durs, 0.99),
                "max": max(durs) if durs else 0.0,
            },
        }

    summary = {
        "scenario": "B_mixed_load",
        "duration_s": round(duration, 2),
        "total": len(samples),
        "success": succ,
        "error_5xx": err5xx,
        "error_rate": round((len(samples) - succ) / len(samples), 4),
        "qps_actual": qps_actual,
        "qps_target": target_qps,
        "endpoint_mix_actual": ep_counter,
        "latency_ms": {
            "avg": round(sum(durations) / len(durations), 2) if durations else 0.0,
            "p50": _percentile(durations, 0.50),
            "p95": _percentile(durations, 0.95),
            "p99": _percentile(durations, 0.99),
            "max": max(durations) if durations else 0.0,
        },
        "endpoint_stats": ep_stats,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    summary_path = out_path.with_suffix(".summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[loadtest_B] raw={out_path} summary={summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

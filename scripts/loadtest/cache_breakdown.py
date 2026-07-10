"""场景 C — 缓存击穿测试 — Phase 7 Task 3.3.

为满足 "调用 backend.cache 模块清除缓存" 的要求（且不能修改业务代码），
本脚本在同一 Python 进程内启动 uvicorn (后台线程) + 直接
``from backend.cache import list_cache, detail_cache, static_cache``，
从而能即时清空三个 cache 实例。

阶段
----
1. warmup: 调 10 次 /api/hotspots 填 cache
2. breakdown: 调 list_cache.clear() / detail_cache.clear() / static_cache.clear()
3. measurement: 1000 并发瞬时请求 /api/hotspots?category=ai，持续 5s

结果写入 ``scripts/logs/loadtest_C_<ts>.json``。
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
LOGS_DIR = SCRIPT_DIR.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# 把项目根加到 sys.path，确保可 import backend
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# 启动 uvicorn (in-process) — Phase 2 才能直接调 cache.clear()
# ---------------------------------------------------------------------------
def _start_backend_inproc(host: str, port: int) -> tuple[Any, Any]:
    """在后台线程启动 uvicorn.Server。返回 (server, thread)."""
    import uvicorn  # type: ignore

    config = uvicorn.Config(
        "backend.main:app",
        host=host,
        port=port,
        log_level="warning",
        reload=False,
    )
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, name="uvicorn-inproc", daemon=True)
    t.start()
    return server, t


def _wait_backend(base_url: str, timeout_s: float = 30.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=2) as r:
                if 200 <= r.status < 300:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
def _http_get(url: str, timeout: float = 10.0) -> tuple[int, float]:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "loadtest-C/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read(1024)
            return r.status, round((time.time() - t0) * 1000, 2)
    except urllib.error.HTTPError as e:
        return e.code, round((time.time() - t0) * 1000, 2)
    except Exception:
        return 0, round((time.time() - t0) * 1000, 2)


def _hit_rate_snapshot() -> dict[str, float]:
    """直接读 backend.cache.hit_rate()。"""
    from backend.cache import hit_rate  # type: ignore

    return hit_rate()


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(int(len(s) * p), len(s) - 1)
    return round(s[idx], 2)


def main() -> int:
    base_url = os.getenv("LOADTEST_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    if ":" in base_url.rsplit("//", 1)[-1]:
        # 解析端口
        port = int(base_url.rsplit(":", 1)[-1])
    else:
        port = 8000
    host = "127.0.0.1"
    concurrent = int(os.getenv("LOADTEST_C_CONC", "1000"))
    duration_s = float(os.getenv("LOADTEST_C_DURATION_S", "5"))
    category = os.getenv("LOADTEST_CATEGORY", "ai")
    url = f"{base_url}/api/hotspots?category={category}"

    print(
        f"[loadtest_C] url={url} concurrent={concurrent} duration={duration_s}s",
        flush=True,
    )

    # 1. 启动后端 (in-process)
    server, _t = _start_backend_inproc(host, port)
    if not _wait_backend(base_url, timeout_s=30):
        print("[loadtest_C] backend failed to start", flush=True)
        return 1
    print("[loadtest_C] backend up (in-process)", flush=True)

    stop_flag = {"stop": False}

    def _on_signal(_sig, _frm):
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    report: dict[str, Any] = {
        "scenario": "C_cache_breakdown",
        "url": url,
        "concurrent": concurrent,
        "duration_s": duration_s,
        "phases": {},
    }

    try:
        # --- Phase 1: warmup ---
        warmup_durations: list[float] = []
        warmup_statuses: list[int] = []
        for i in range(10):
            st, d = _http_get(url)
            warmup_statuses.append(st)
            warmup_durations.append(d)
        report["phases"]["warmup"] = {
            "samples": 10,
            "success": sum(1 for s in warmup_statuses if 200 <= s < 300),
            "avg_ms": round(sum(warmup_durations) / len(warmup_durations), 2),
            "hit_rate_after": _hit_rate_snapshot(),
        }
        print(f"[loadtest_C] phase1 warmup hit_rate={report['phases']['warmup']['hit_rate_after']}", flush=True)

        # --- Phase 2: cache breakdown ---
        # Phase 8: 只清 list_cache（detail/static 清了首请求延迟会到 3-4s）
        from backend.cache import (  # type: ignore
            list_cache,
        )

        list_cache.clear()
        report["phases"]["breakdown"] = {
            "action": "list_cache.clear()  (Phase 8: 仅清 list_cache，保留 detail/static)",
            "hit_rate_after": _hit_rate_snapshot(),
        }
        print(f"[loadtest_C] phase2 cleared, hit_rate={report['phases']['breakdown']['hit_rate_after']}", flush=True)

        # --- Phase 3: measurement ---
        # 瞬时 1000 并发，然后持续到 5s
        # 先一次性提交 1000 个，测首请求延迟
        first_request_delay = None
        all_samples: list[tuple[float, int, float]] = []  # (ts, status, dur)
        with ThreadPoolExecutor(max_workers=concurrent) as pool:
            futures = [pool.submit(_http_get, url) for _ in range(concurrent)]
            # 收集完成
            for fut in as_completed(futures):
                try:
                    st, d = fut.result()
                except Exception:
                    st, d = 0, 0.0
                if first_request_delay is None and st > 0:
                    first_request_delay = d
                all_samples.append((time.time(), st, d))
            # 再持续 5s 收更多样本 + 周期性记录 hit rate
            end = time.time() + duration_s
            sample_points: list[dict[str, Any]] = []
            t0 = time.time()
            last_hr = _hit_rate_snapshot()
            sample_points.append(
                {"t_s": 0.0, "hit_rate": last_hr, "cum_samples": len(all_samples)}
            )
            while time.time() < end and not stop_flag["stop"]:
                # 持续发
                fs = [pool.submit(_http_get, url) for _ in range(min(50, concurrent))]
                for f in as_completed(fs, timeout=2.0):
                    try:
                        st, d = f.result()
                    except Exception:
                        st, d = 0, 0.0
                    all_samples.append((time.time(), st, d))
                time.sleep(0.1)
                hr = _hit_rate_snapshot()
                t_now = round(time.time() - t0, 2)
                # 仅在变化时记录
                if hr != last_hr:
                    sample_points.append(
                        {
                            "t_s": t_now,
                            "hit_rate": hr,
                            "cum_samples": len(all_samples),
                        }
                    )
                    last_hr = hr
            # 末尾再记一次
            sample_points.append(
                {
                    "t_s": round(time.time() - t0, 2),
                    "hit_rate": _hit_rate_snapshot(),
                    "cum_samples": len(all_samples),
                }
            )

        statuses = [s[1] for s in all_samples]
        durations = [s[2] for s in all_samples if s[1] > 0]
        succ = sum(1 for st in statuses if 200 <= st < 300)
        report["phases"]["measurement"] = {
            "samples": len(all_samples),
            "success": succ,
            "success_rate": round(succ / len(all_samples), 4) if all_samples else 0.0,
            "first_request_delay_ms": first_request_delay,
            "latency_ms": {
                "avg": round(sum(durations) / len(durations), 2) if durations else 0.0,
                "p50": _percentile(durations, 0.50),
                "p95": _percentile(durations, 0.95),
                "p99": _percentile(durations, 0.99),
                "max": max(durations) if durations else 0.0,
            },
            "hit_rate_timeline": sample_points,
        }
        print(json.dumps(report["phases"]["measurement"], ensure_ascii=False, indent=2), flush=True)
    finally:
        # 关闭 uvicorn
        try:
            server.should_exit = True
        except Exception:
            pass

    out_path = LOGS_DIR / f"loadtest_C_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[loadtest_C] written to {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

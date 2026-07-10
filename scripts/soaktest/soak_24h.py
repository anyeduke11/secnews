"""24h 连续运行浸泡测试 — Phase 7 Task 2.

启动 backend (subprocess) + metrics_collector + health_probe (后台子进程)
+ 前端用户模拟器（每 30min 调 7 个分类 + 关键词搜索）。运行 SOAK_HOURS
小时后优雅关闭。

环境变量
--------
- ``SOAK_HOURS``         总运行时长 (小时, 默认 24, 0.083 = 5min 用于快速验证)
- ``SOAK_INTERVAL_MIN``  前端模拟器调用间隔 (分钟, 默认 30)
- ``SOAK_BASE_URL``      后端 base URL, 默认 http://127.0.0.1:8000
- ``SOAK_PORT``          启动后端端口, 默认 8000
- ``SOAK_HEALTH_INT``    health_probe 间隔 (秒, 默认 30)
- ``SOAK_METRICS_INT``   metrics_collector 间隔 (秒, 默认 60)

用法
----
    $ python scripts/soaktest/soak_24h.py                       # 24h
    $ SOAK_HOURS=0.083 python scripts/soaktest/soak_24h.py      # 5min
    $ SOAK_HOURS=1 SOAK_INTERVAL_MIN=1 python scripts/soaktest/soak_24h.py
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
LOGS_DIR = SCRIPT_DIR.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

PROJECT_ROOT = SCRIPT_DIR.parent.parent
COMMON_DIR = SCRIPT_DIR.parent / "common"

# 7 个分类（含 "all"）
CATEGORIES: list[str] = ["ai", "security", "finance", "startup", "bid", "github", "all"]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wait_for_backend(base_url: str, timeout_s: float = 60.0) -> bool:
    """轮询 /api/health 直到返回 2xx 或超时。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=2) as r:
                if 200 <= r.status < 300:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(1)
    return False


def _http_get_json(url: str, timeout: float = 5.0) -> tuple[int, float, Any]:
    """GET 一个 URL，返回 (status, duration_ms, body_or_error)."""
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read()
            try:
                parsed = json.loads(body.decode("utf-8", errors="replace"))
            except Exception:
                parsed = body[:200].decode("utf-8", errors="replace")
            return r.status, round((time.time() - t0) * 1000, 1), parsed
    except urllib.error.HTTPError as e:
        return e.code, round((time.time() - t0) * 1000, 1), str(e)[:200]
    except Exception as e:
        return 0, round((time.time() - t0) * 1000, 1), f"{type(e).__name__}: {str(e)[:100]}"


# ---------------------------------------------------------------------------
# 前端模拟器
# ---------------------------------------------------------------------------
class FrontendSimulator:
    """每 ``interval_min`` 分钟循环调 7 个分类 + 1 个关键词搜索。"""

    def __init__(self, base_url: str, interval_min: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.interval_s = max(interval_min * 60, 5.0)  # 至少 5s 间隔避免太快
        self.samples: list[dict[str, Any]] = []
        self._stop = False
        self._thread = None
        import threading
        self._thread = threading.Thread(
            target=self._run, name="frontend-sim", daemon=True
        )

    def start(self) -> None:
        if self._thread is not None:
            self._thread.start()

    def stop(self) -> None:
        self._stop = True

    def _run(self) -> None:
        # 立即跑一轮 warmup
        self._hit_all()
        while not self._stop:
            # sleep 切片便于快速响应停止
            slept = 0.0
            while slept < self.interval_s and not self._stop:
                time.sleep(min(1.0, self.interval_s - slept))
                slept += 1.0
            if self._stop:
                break
            self._hit_all()

    def _hit_all(self) -> None:
        for cat in CATEGORIES:
            status, dur, _ = _http_get_json(
                f"{self.base_url}/api/hotspots?category={cat}"
            )
            self.samples.append(
                {
                    "ts": _now_iso(),
                    "kind": "list",
                    "url": f"/api/hotspots?category={cat}",
                    "status": status,
                    "duration_ms": dur,
                }
            )
        # 关键词搜索
        status, dur, _ = _http_get_json(
            f"{self.base_url}/api/hotspots?keyword=test"
        )
        self.samples.append(
            {
                "ts": _now_iso(),
                "kind": "search",
                "url": "/api/hotspots?keyword=test",
                "status": status,
                "duration_ms": dur,
            }
        )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    soak_hours = float(os.getenv("SOAK_HOURS", "24"))
    interval_min = float(os.getenv("SOAK_INTERVAL_MIN", "30"))
    base_url = os.getenv("SOAK_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    port = int(os.getenv("SOAK_PORT", "8000"))
    health_int = int(os.getenv("SOAK_HEALTH_INT", "30"))
    metrics_int = int(os.getenv("SOAK_METRICS_INT", "60"))

    # 如果 base_url 没指定端口但指定了 PORT，强制使用
    if port != 8000 and ":8000" in base_url:
        base_url = base_url.replace(":8000", f":{port}")

    deadline_ts = time.time() + soak_hours * 3600
    started_at = _now_iso()
    print(
        f"[soak] start hours={soak_hours} interval_min={interval_min} "
        f"base_url={base_url} deadline={deadline_ts}",
        flush=True,
    )

    # 0. 采样初始 RSS (soak 进程) + DB size
    try:
        import psutil  # type: ignore

        _rss0_mb = round(psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024, 2)
    except Exception:
        _rss0_mb = 0.0
    _db0_mb = 0.0
    try:
        _status, _d, _b = _http_get_json(f"{base_url}/api/health", timeout=5.0)
        if isinstance(_b, dict):
            _db0_mb = float(_b.get("components", {}).get("db", {}).get("size_mb", 0.0) or 0.0)
    except Exception:
        pass

    # 1. 启动后端
    env = os.environ.copy()
    env["PORT"] = str(port)
    backend_log = LOGS_DIR / f"soak_backend_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    backend_proc = subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=open(backend_log, "ab", buffering=0),
        stderr=subprocess.STDOUT,
    )
    print(f"[soak] backend pid={backend_proc.pid} log={backend_log}", flush=True)

    # 2. 等待就绪
    if not _wait_for_backend(base_url, timeout_s=60.0):
        print(f"[soak] backend failed to start within 60s, abort", flush=True)
        backend_proc.terminate()
        backend_proc.wait(timeout=5)
        return 1

    # 3. 启动 health_probe + metrics_collector 子进程
    health_proc = subprocess.Popen(
        [sys.executable, str(COMMON_DIR / "health_probe.py")],
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "HEALTH_INTERVAL": str(health_int),
             "BASE_URL": base_url},
    )
    metrics_proc = subprocess.Popen(
        [sys.executable, str(COMMON_DIR / "metrics_collector.py")],
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "METRICS_INTERVAL": str(metrics_int),
             "BASE_URL": base_url},
    )
    print(
        f"[soak] health_probe pid={health_proc.pid} "
        f"metrics_collector pid={metrics_proc.pid}",
        flush=True,
    )

    # 4. 启动前端模拟器
    sim = FrontendSimulator(base_url, interval_min)
    sim.start()

    # 5. 信号处理
    stop_flag = {"stop": False}

    def _on_signal(_sig, _frm):
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    # 6. 主循环等到 deadline 或 stop
    try:
        while not stop_flag["stop"] and time.time() < deadline_ts:
            if backend_proc.poll() is not None:
                print(
                    f"[soak] backend exited unexpectedly rc={backend_proc.returncode}",
                    flush=True,
                )
                break
            time.sleep(2.0)
    finally:
        # 7. 关闭前端模拟器
        sim.stop()
        # 8. SIGTERM 监控子进程
        for p in (health_proc, metrics_proc):
            try:
                p.terminate()
            except Exception:
                pass
        for p in (health_proc, metrics_proc):
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()

        # 9. 优雅关闭后端 (SIGTERM 等 10s)
        if backend_proc.poll() is None:
            print("[soak] terminating backend (SIGTERM, 10s grace)...", flush=True)
            try:
                backend_proc.terminate()
                backend_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print("[soak] backend did not exit in 10s, killing", flush=True)
                backend_proc.kill()
                backend_proc.wait(timeout=5)

    # 10. 汇总
    finished_at = _now_iso()
    samples = sim.samples
    total = len(samples)
    succ = sum(1 for s in samples if 200 <= s["status"] < 300)
    durations = [s["duration_ms"] for s in samples if s["status"] > 0]
    avg_ms = round(sum(durations) / len(durations), 1) if durations else 0.0
    p95 = sorted(durations)[int(len(durations) * 0.95)] if durations else 0
    p99 = sorted(durations)[int(len(durations) * 0.99)] if durations else 0

    # 拉最后一次健康数据用于 hit rate
    final_hit_rate = 0.0
    final_rss_mb = 0.0
    final_db_mb = 0.0
    try:
        _status, _d, body = _http_get_json(f"{base_url}/api/health", timeout=5.0)
        if isinstance(body, dict):
            rates = body.get("components", {}).get("cache", {}).get("hit_rate", {})
            if isinstance(rates, dict):
                # 简单平均三个 cache
                vals = [v for v in rates.values() if isinstance(v, (int, float))]
                final_hit_rate = round(sum(vals) / len(vals), 4) if vals else 0.0
            db = body.get("components", {}).get("db", {})
            final_db_mb = float(db.get("size_mb", 0.0) or 0.0)
    except Exception:
        pass

    # 采样 soak 进程 RSS (最终)
    try:
        import psutil  # type: ignore

        final_rss_mb = round(psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024, 2)
    except Exception:
        final_rss_mb = 0.0

    # 计算增长 (后端 RSS 我们通过 metrics_collector 间接记录,这里只取本进程)
    memory_growth_mb = round(final_rss_mb - _rss0_mb, 2)
    db_growth_mb = round(final_db_mb - _db0_mb, 2)

    summary = {
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_hours": round(
            (datetime.fromisoformat(finished_at).timestamp()
             - datetime.fromisoformat(started_at).timestamp()) / 3600,
            4,
        ),
        "config": {
            "soak_hours": soak_hours,
            "interval_min": interval_min,
            "base_url": base_url,
        },
        "frontend_samples": total,
        "frontend_success": succ,
        "frontend_success_rate": round(succ / total, 4) if total else 0.0,
        "frontend_latency_ms": {
            "avg": avg_ms,
            "p95": p95,
            "p99": p99,
            "max": max(durations) if durations else 0,
        },
        "memory_growth_mb": memory_growth_mb,
        "db_growth_mb": db_growth_mb,
        "final_cache_hit_rate": final_hit_rate,
        "final_db_size_mb": final_db_mb,
        "backend_returncode": backend_proc.returncode,
    }

    out_path = LOGS_DIR / f"soak_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[soak] summary written to {out_path}", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

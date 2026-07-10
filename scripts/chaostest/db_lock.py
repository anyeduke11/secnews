"""故障演练 2 — SQLite database is locked — Phase 7 Task 4.2.

模拟 2 个线程同时 ``BEGIN IMMEDIATE; INSERT INTO hotspots; COMMIT;``
触发 SQLite 锁竞争。busy_timeout=5000 应让写入自动重试。

验证：
- 后端 API 仍能响应 200（无 500）
- busy_timeout 生效，等待后写入成功
- 测量 API 响应时间

结果写入 ``scripts/logs/chaos_2_<ts>.json``。
"""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
LOGS_DIR = SCRIPT_DIR.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
def _do_insert(db_path: str, label: str, insert_log: list[dict], stop_evt: threading.Event) -> None:
    """独立线程：开连接 → 循环 BEGIN IMMEDIATE → INSERT → COMMIT。"""
    try:
        conn = sqlite3.connect(
            db_path, timeout=10.0, isolation_level=None, check_same_thread=True
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        i = 0
        while not stop_evt.is_set() and i < 50:
            i += 1
            t0 = time.time()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT OR REPLACE INTO hotspots (id, title, source, url, category, published_at, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"chaos_{label}_{int(time.time()*1000)}_{i}",
                        f"chaos insert from {label} #{i}",
                        f"chaos-{label}",
                        f"https://example.com/chaos/{label}/{i}",
                        "ai",
                        datetime.utcnow().isoformat() + "Z",
                        datetime.utcnow().isoformat() + "Z",
                    ),
                )
                conn.execute("COMMIT")
                dur_ms = round((time.time() - t0) * 1000, 2)
                insert_log.append(
                    {
                        "thread": label,
                        "i": i,
                        "ok": True,
                        "duration_ms": dur_ms,
                        "ts": datetime.utcnow().isoformat() + "Z",
                    }
                )
            except sqlite3.OperationalError as e:
                conn.execute("ROLLBACK")
                dur_ms = round((time.time() - t0) * 1000, 2)
                insert_log.append(
                    {
                        "thread": label,
                        "i": i,
                        "ok": False,
                        "error": str(e)[:200],
                        "duration_ms": dur_ms,
                        "ts": datetime.utcnow().isoformat() + "Z",
                    }
                )
            time.sleep(0.01)
        conn.close()
    except Exception as e:
        insert_log.append(
            {"thread": label, "fatal": True, "error": str(e)[:200], "ts": datetime.utcnow().isoformat() + "Z"}
        )


# ---------------------------------------------------------------------------
def _start_backend_subprocess(port: int) -> Any:
    """在子进程启动 run.py。"""
    import subprocess

    env = os.environ.copy()
    env["PORT"] = str(port)
    return subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


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


def _http_get(url: str, timeout: float = 10.0) -> tuple[int, float]:
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read(2048)
            return r.status, round((time.time() - t0) * 1000, 2)
    except urllib.error.HTTPError as e:
        return e.code, round((time.time() - t0) * 1000, 2)
    except Exception:
        return 0, round((time.time() - t0) * 1000, 2)


# ---------------------------------------------------------------------------
def main() -> int:
    out_path = LOGS_DIR / f"chaos_2_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    report: dict[str, Any] = {
        "scenario": "chaos_2_db_lock",
        "started_at": datetime.utcnow().isoformat() + "Z",
    }

    # 配置
    base_url = os.getenv("CHAOS_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    port = int(base_url.rsplit(":", 1)[-1]) if ":" in base_url.rsplit("//", 1)[-1] else 8000
    db_path = os.getenv("CHAOS_DB_PATH", str(PROJECT_ROOT / "backend" / "hotspot.db"))
    duration_s = float(os.getenv("CHAOS_DURATION_S", "5"))

    # 找现成后端；没起就自起
    proc = None
    try:
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=2) as r:
            if r.status == 200:
                print(f"[chaos_2] using existing backend at {base_url}", flush=True)
    except Exception:
        print(f"[chaos_2] no existing backend, starting one on port {port}", flush=True)
        proc = _start_backend_subprocess(port)
        if not _wait_backend(base_url, timeout_s=30):
            report["error"] = "backend failed to start"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            return 1

    # 信号
    stop_flag = {"stop": False}

    def _on_signal(_sig, _frm):
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    insert_log: list[dict] = []
    stop_evt = threading.Event()
    t1 = threading.Thread(target=_do_insert, args=(db_path, "A", insert_log, stop_evt), daemon=True)
    t2 = threading.Thread(target=_do_insert, args=(db_path, "B", insert_log, stop_evt), daemon=True)
    t1.start()
    t2.start()

    # 在锁竞争期间打 API
    api_samples: list[tuple[float, int, float]] = []
    end = time.time() + duration_s
    while time.time() < end and not stop_flag["stop"]:
        st, d = _http_get(f"{base_url}/api/hotspots?category=ai")
        api_samples.append((time.time(), st, d))
        time.sleep(0.1)

    # 等线程结束
    stop_evt.set()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # 后端关（如自起）
    if proc is not None:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # 汇总
    api_statuses = [s[1] for s in api_samples]
    api_durs = [s[2] for s in api_samples if s[1] > 0]
    api_ok = sum(1 for s in api_statuses if 200 <= s < 300)
    api_500 = sum(1 for s in api_statuses if 500 <= s < 600)

    insert_ok = sum(1 for x in insert_log if x.get("ok"))
    insert_fail = sum(1 for x in insert_log if not x.get("ok") and "fatal" not in x)
    max_insert_dur = max((x.get("duration_ms", 0) or 0) for x in insert_log) if insert_log else 0.0

    report.update(
        {
            "finished_at": datetime.utcnow().isoformat() + "Z",
            "duration_s": duration_s,
            "db_path": db_path,
            "insert_log": insert_log[:200],  # 截断避免文件过大
            "insert_count": len(insert_log),
            "insert_success": insert_ok,
            "insert_fail": insert_fail,
            "max_insert_duration_ms": max_insert_dur,
            "api_count": len(api_samples),
            "api_ok": api_ok,
            "api_500": api_500,
            "api_latency_ms": {
                "avg": round(sum(api_durs) / len(api_durs), 2) if api_durs else 0.0,
                "p50": sorted(api_durs)[len(api_durs) // 2] if api_durs else 0.0,
                "p95": sorted(api_durs)[int(len(api_durs) * 0.95)] if api_durs else 0.0,
                "p99": sorted(api_durs)[int(len(api_durs) * 0.99)] if api_durs else 0.0,
                "max": max(api_durs) if api_durs else 0.0,
            },
            "pass": api_500 == 0 and api_ok > 0,
        }
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[chaos_2] pass={report['pass']} report={out_path}", flush=True)
    print(json.dumps({k: v for k, v in report.items() if k not in ("insert_log",)}, ensure_ascii=False, indent=2), flush=True)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

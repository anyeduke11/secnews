"""Metrics collector: 采集后端进程的 RSS / CPU / DB size / cache stats.

每 60s 调用一次：
- /api/health  → db.size_mb, cache.hit_rate, uptime_s
- psutil       → RSS, CPU%
- os.stat      → hotspot.db 文件大小

写入 scripts/logs/metrics_YYYYMMDD_HHMMSS.jsonl
"""
import os
import sys
import time
import json
import signal
import psutil
import requests
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def collect_once(base_url: str = "http://127.0.0.1:8000") -> dict:
    """单次采集快照。"""
    sample = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "uptime_s": 0,
        "rss_mb": 0.0,
        "cpu_pct": 0.0,
        "db_size_mb": 0.0,
        "cache_hit_rate": 0.0,
    }
    try:
        # /api/health
        r = requests.get(f"{base_url}/api/health", timeout=5)
        if r.ok:
            data = r.json()
            sample["uptime_s"] = data.get("uptime_s", 0)
            sample["db_size_mb"] = data.get("db", {}).get("size_mb", 0)
            sample["cache_hit_rate"] = data.get("cache", {}).get("hit_rate", 0)
    except Exception as e:
        sample["health_error"] = str(e)[:100]

    try:
        proc = psutil.Process(os.getppid())
        sample["rss_mb"] = round(proc.memory_info().rss / 1024 / 1024, 2)
        sample["cpu_pct"] = round(proc.cpu_percent(interval=0.1), 1)
    except Exception:
        pass

    return sample


def run_collector(interval_s: int = 60, base_url: str = "http://127.0.0.1:8000") -> None:
    """主循环。"""
    log_file = LOG_DIR / f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    print(f"[metrics_collector] logging to {log_file}")
    running = {"flag": True}

    def stop(*_):
        running["flag"] = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    with open(log_file, "a", encoding="utf-8") as f:
        while running["flag"]:
            try:
                sample = collect_once(base_url)
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                f.flush()
                print(f"[metrics] {sample['ts']} RSS={sample['rss_mb']}MB "
                      f"DB={sample['db_size_mb']}MB hit={sample['cache_hit_rate']}")
            except Exception as e:
                print(f"[metrics] error: {e}")
            for _ in range(interval_s):
                if not running["flag"]:
                    break
                time.sleep(1)
    print("[metrics_collector] stopped")


if __name__ == "__main__":
    interval = int(os.getenv("METRICS_INTERVAL", "60"))
    run_collector(interval)

"""Health probe: 每 30s 探测一次 /api/health, 记录状态码 + 延迟."""
import os
import time
import json
import signal
import requests
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def run_probe(interval_s: int = 30, base_url: str = "http://127.0.0.1:8000") -> None:
    log_file = LOG_DIR / f"health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    print(f"[health_probe] logging to {log_file}")
    running = {"flag": True}

    def stop(*_):
        running["flag"] = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    with open(log_file, "a", encoding="utf-8") as f:
        while running["flag"]:
            sample = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "endpoint": "/api/health",
            }
            try:
                t0 = time.time()
                r = requests.get(f"{base_url}/api/health", timeout=10)
                sample["duration_ms"] = round((time.time() - t0) * 1000, 1)
                sample["status_code"] = r.status_code
                if r.ok:
                    body = r.json()
                    sample["db_status"] = body.get("db", {}).get("integrity", "unknown")
                    sample["cache_hit_rate"] = body.get("cache", {}).get("hit_rate", 0)
            except Exception as e:
                sample["error"] = str(e)[:100]
                sample["status_code"] = 0
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            f.flush()
            for _ in range(interval_s):
                if not running["flag"]:
                    break
                time.sleep(1)
    print("[health_probe] stopped")


if __name__ == "__main__":
    interval = int(os.getenv("HEALTH_INTERVAL", "30"))
    run_probe(interval)

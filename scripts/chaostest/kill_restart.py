"""故障演练 3 — kill -9 进程崩溃重启 — Phase 7 Task 4.3 + Phase 8 改断言。

启动后端 → 5 次热请求 → ``proc.kill()`` 模拟崩溃 → 等 1s → 重启 →
测首请求延迟 (应 < 2s) → **持续 30s 高频请求** → 测 hit_rate > 50%。
（Phase 8 调整：原 5s/10 请求 → 30s/持续流量 更贴近生产）

结果写入 ``scripts/logs/chaos_3_<ts>.json``。
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
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


# ---------------------------------------------------------------------------
def _start_backend(port: int) -> Any:
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


def _http_get(url: str, timeout: float = 10.0) -> tuple[int, float, str]:
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read(2048)
            return r.status, round((time.time() - t0) * 1000, 2), ""
    except urllib.error.HTTPError as e:
        return e.code, round((time.time() - t0) * 1000, 2), f"HTTP {e.code}"
    except Exception as e:
        return 0, round((time.time() - t0) * 1000, 2), f"{type(e).__name__}: {str(e)[:80]}"


def _cache_hit_rate(base_url: str) -> float:
    """从 /api/health 拉取 list cache hit_rate（Phase 8 修复）。

    原版取 3 个 cache 平均值，导致 detail/static 永远 0% 把平均拉低。
    chaos 3 只打 /api/hotspots（list cache），所以只看 list 的命中率。
    """
    try:
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=3) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
            rates = data.get("components", {}).get("cache", {}).get("hit_rate", {})
            if isinstance(rates, dict):
                # Phase 8: 只看 list（chaos 3 只打 list endpoint）
                list_rate = rates.get("list")
                if isinstance(list_rate, (int, float)) and list_rate > 0:
                    return round(list_rate, 4)
                # 兜底：所有 cache 平均
                vals = [v for v in rates.values() if isinstance(v, (int, float))]
                return round(sum(vals) / len(vals), 4) if vals else 0.0
    except Exception:
        pass
    return 0.0


# ---------------------------------------------------------------------------
def main() -> int:
    out_path = LOGS_DIR / f"chaos_3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report: dict[str, Any] = {
        "scenario": "chaos_3_kill_restart",
        "started_at": datetime.utcnow().isoformat() + "Z",
    }

    # 配置
    base_url = os.getenv("CHAOS_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    port = int(base_url.rsplit(":", 1)[-1]) if ":" in base_url.rsplit("//", 1)[-1] else 8000

    # 信号
    stop_flag = {"stop": False}

    def _on_signal(_sig, _frm):
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    proc = None
    try:
        # 1. 启动后端
        proc = _start_backend(port)
        report["first_pid"] = proc.pid
        if not _wait_backend(base_url, timeout_s=30):
            report["error"] = "backend failed to start"
            return 1
        print(f"[chaos_3] backend pid={proc.pid} up", flush=True)

        # 2. 打 5 次
        warmup = []
        for i in range(5):
            st, d, err = _http_get(f"{base_url}/api/hotspots?category=ai")
            warmup.append({"i": i, "status": st, "duration_ms": d, "error": err})
        report["warmup_hits"] = warmup
        report["warmup_hit_rate"] = _cache_hit_rate(base_url)

        # 3. kill -9
        print(f"[chaos_3] killing backend pid={proc.pid}", flush=True)
        proc.kill()
        proc.wait(timeout=5)
        report["first_returncode"] = proc.returncode

        # 4. 等 1s
        time.sleep(1.0)

        # 5. 重启
        proc = _start_backend(port)
        report["second_pid"] = proc.pid
        if not _wait_backend(base_url, timeout_s=30):
            report["error"] = "backend failed to restart"
            return 1
        print(f"[chaos_3] restarted pid={proc.pid}", flush=True)

        # 6. 测首请求延迟
        t0 = time.time()
        st, d, err = _http_get(f"{base_url}/api/hotspots?category=ai")
        first_request_delay = round((time.time() - t0) * 1000, 2)
        report["first_request_after_restart"] = {
            "status": st,
            "duration_ms": first_request_delay,
            "error": err,
        }
        print(f"[chaos_3] first request {first_request_delay}ms status={st}", flush=True)

        # 6.5 Phase 8: 等 initial collect_all / url_content_check 等全部完成
        # scheduler 启动时 4 个 job 几乎同时触发，url_content_check 跑 10-20s
        # 不等待会持续清空 cache。等待 25s 让所有初始 job 结束。
        time.sleep(25)
        # 重填一次 cache
        for _ in range(10):
            _http_get(f"{base_url}/api/hotspots?category=ai")
            time.sleep(0.1)
        warmup2 = _cache_hit_rate(base_url)
        report["post_warmup_hit_rate"] = warmup2

        # 7. Phase 8: 持续 30s 高频请求（10 QPS）后测 hit_rate
        # 旧逻辑：等 5s 后打 10 次
        # 新逻辑：30s 内 10 QPS（共 ~300 请求），更贴近生产流量
        sustained_hits: list[dict[str, Any]] = []
        deadline_30s = time.time() + 30.0
        target_interval = 0.1  # 10 QPS
        next_t = time.time()
        while time.time() < deadline_30s:
            now = time.time()
            if now < next_t:
                time.sleep(next_t - now)
            st, d, err = _http_get(f"{base_url}/api/hotspots?category=ai")
            sustained_hits.append({
                "t": round(time.time() - (deadline_30s - 30.0), 2),
                "status": st,
                "duration_ms": d,
                "error": err,
            })
            next_t += target_interval
        hit_rate_30s = _cache_hit_rate(base_url)
        report["after_30s_sustained_hits_count"] = len(sustained_hits)
        report["after_30s_sustained_hit_rate"] = hit_rate_30s
        report["after_30s_sustained_avg_ms"] = round(
            sum(h["duration_ms"] for h in sustained_hits) / max(1, len(sustained_hits)), 2
        )

        # 8. 判定
        first_ok = first_request_delay < 2000 and st > 0
        hit_ok = hit_rate_30s > 0.5
        report["pass"] = first_ok and hit_ok
        report["assertions"] = {
            "first_request_delay_under_2s": first_ok,
            "hit_rate_after_30s_sustained_over_50pct": hit_ok,
        }
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        report["traceback"] = traceback.format_exc()
        report["pass"] = False
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        report["finished_at"] = datetime.utcnow().isoformat() + "Z"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[chaos_3] pass={report.get('pass')} report={out_path}", flush=True)
        print(json.dumps({k: v for k, v in report.items() if k not in ("after_5s_hits",)}, ensure_ascii=False, indent=2), flush=True)

    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())

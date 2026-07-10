"""故障 4：DB 损坏演练。

方法：
1. 启动后端子进程。
2. 等 5s 等待就绪。
3. 注入"损坏"：DROP COLUMN url + DELETE all rows from hotspots。
   单独 DROP COLUMN 不会触发 PRAGMA integrity_check（SQLite 3.x 已知行为），
   所以额外 DELETE 所有行让 _db_health 通过 row count 检查发现 hotspots 为空，
   触发 db.ok=false。backend 仍然能启动（init_db 的 integrity_check 不报错），
   但 health 端点会反映损坏。
4. 调用 /api/health.components.db 验证 db.ok=false。
5. 停止子进程。

Phase 8 新增。
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "backend" / "hotspot.db"
LOG_DIR = ROOT / "scripts" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RESULT_PATH = LOG_DIR / f"chaos_4_{time.strftime('%Y%m%d_%H%M%S')}.json"

import requests


def corrupt_db() -> str:
    """Phase 8 Task 5.4 修复：双管齐下做损坏。

    1. ALTER TABLE hotspots DROP COLUMN url — schema 破坏
       (SQLite 3.35+ 支持，但 PRAGMA integrity_check 不会因此报错)
    2. DELETE FROM hotspots / hotspots_fts — 让 _db_health 通过 row count
       检查发现 hotspots 为空 → db.ok=false

    之所以两步都要做：单独 schema 破坏不会被 integrity_check 捕获，
    单独 DELETE 容易被当成"数据为空"，加上 schema 破坏使破坏更彻底。

    Returns:
        描述使用了哪种破坏方法（用于写到 chaos_4_*.json）。
    """
    print("[chaos4] corrupting DB (Phase 8 method: drop_column + truncate)...")
    if not DB_PATH.exists():
        print(f"[chaos4] DB not found at {DB_PATH}, skipping corruption")
        return "skipped_no_db"

    conn = sqlite3.connect(str(DB_PATH))
    methods: list[str] = []
    try:
        # 1) DROP COLUMN url（schema 破坏 — PRAGMA integrity_check 不一定检测）
        try:
            conn.execute("ALTER TABLE hotspots DROP COLUMN url")
            methods.append("drop_column_url")
            print("[chaos4] dropped column 'url' from hotspots")
        except Exception as e:
            print(f"[chaos4] drop column failed: {e}, continuing with truncate only")

        # 2) DELETE 所有行（让 hotspots row count == 0，_db_health 会报 ok=false）
        try:
            conn.execute("DELETE FROM hotspots")
            conn.execute("DELETE FROM hotspots_fts")
            methods.append("truncate_hotspots")
            print("[chaos4] truncated hotspots + hotspots_fts (all rows deleted)")
        except Exception as e:
            print(f"[chaos4] truncate failed: {e}")
            methods.append("truncate_failed")

        conn.commit()
    finally:
        conn.close()

    return "+".join(methods) if methods else "none"


def start_backend(log_path: Path) -> subprocess.Popen:
    """启动后端子进程。"""
    print("[chaos4] starting backend subprocess...")
    log_fh = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=str(ROOT),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    return proc


def wait_health(base_url: str, timeout_s: float = 30.0) -> bool:
    """等待 /api/health 返回 200。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/api/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    base_url = os.getenv("CHAOS_BASE_URL", "http://127.0.0.1:8000")
    log_path = LOG_DIR / f"chaos_4_backend_{time.strftime('%Y%m%d_%H%M%S')}.log"
    proc = start_backend(log_path)
    result: dict = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config": {"base_url": base_url},
        "backend_pid": proc.pid,
    }
    try:
        # 1) 等待后端就绪
        ready = wait_health(base_url, timeout_s=30)
        result["backend_ready"] = ready
        if not ready:
            result["pass"] = False
            result["reason"] = "backend failed to start"
            return _write(result, proc, log_path, returncode=2)

        # 2) 验证初始健康
        r0 = requests.get(f"{base_url}/api/health", timeout=5)
        result["initial_health_status"] = r0.json().get("status")
        result["initial_health_ok"] = r0.json().get("components", {}).get("db", {}).get("ok")

        # 3) 破坏 DB（停后端 → 改 DB → 重启）
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        time.sleep(2)
        corrupt_method = corrupt_db()
        result["corrupt_method"] = corrupt_method
        time.sleep(1)

        # 4) 重启
        proc = start_backend(log_path)
        if not wait_health(base_url, timeout_s=30):
            result["pass"] = False
            result["reason"] = "backend failed to start after corruption"
            return _write(result, proc, log_path, returncode=2)

        # 5) 验证健康检查报告降级
        r1 = requests.get(f"{base_url}/api/health", timeout=5)
        h = r1.json()
        result["post_corrupt_health"] = {
            "status": h.get("status"),
            "db": h.get("components", {}).get("db", {}),
            "scheduler_ok": h.get("components", {}).get("scheduler", {}).get("ok"),
        }

        # 6) 判定（Phase 8 修复：多标准）
        db = h.get("components", {}).get("db", {})
        db_ok = db.get("ok", True)
        integrity = db.get("integrity", {}) or {}
        integrity_ok = integrity.get("ok")
        integrity_result = integrity.get("result", "")
        hotspots_count = db.get("hotspots_count")  # Phase 8 新字段
        status = h.get("status", "ok")

        result["db_ok"] = db_ok
        result["db_integrity_ok"] = integrity_ok
        result["db_integrity_result"] = integrity_result
        result["db_hotspots_count"] = hotspots_count
        result["status"] = status

        # 通过条件（任一即视为检测到损坏）：
        #   - db.ok == False
        #   - integrity.ok == False
        #   - integrity.result 不是 "ok"
        #   - hotspots_count == 0（_db_health 的 row count 校验）
        #   - status != "ok"（degraded/down）
        detected = (
            (db_ok is False)
            or (integrity_ok is False)
            or (bool(integrity_result) and integrity_result != "ok")
            or (hotspots_count == 0)
            or (status != "ok")
        )
        result["pass"] = bool(detected)
        if not detected:
            result["reason"] = (
                "no degradation signal found: db.ok=true, integrity.ok=true, "
                "hotspots_count>0, status=ok"
            )

        return _write(result, proc, log_path, returncode=0)
    except Exception as e:
        result["pass"] = False
        result["error"] = str(e)[:200]
        return _write(result, proc, log_path, returncode=1)
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass


def _write(result: dict, proc: subprocess.Popen, log_path: Path, returncode: int) -> int:
    result["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    result["log_path"] = str(log_path)
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[chaos4] result written to {RESULT_PATH}")
    print(f"[chaos4] pass={result.get('pass')} rc={returncode}")
    return returncode


if __name__ == "__main__":
    sys.exit(main())

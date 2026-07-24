"""v1.7 Phase 5 — Agent CLI (hotspot-agent).

Subcommands:
  start   - Start the poller daemon (foreground)
  stop    - Stop the poller daemon (writes .pid file)
  status  - Show current status
  run-once - Run one polling cycle and exit (testing/debug)

Standalone process that talks to the hotspot backend via HTTP.
Independent of uvicorn / FastAPI lifecycle.

Run: python -m agent.cli start
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from agent.client import HotspotClient
from agent.executor import execute_task
from agent.poller import AgentPoller

# PID file for daemon management
PID_FILE = Path(".hotspot-agent.pid")
LOG_FILE = Path(".hotspot-agent.log")


def _read_pid() -> Optional[int]:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def cmd_start(args: argparse.Namespace) -> int:
    """Start the agent poller (foreground)."""
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"agent already running (pid={pid})")
        return 1
    if PID_FILE.exists():
        PID_FILE.unlink()

    print(f"starting hotspot-agent (base_url={args.base_url})")
    PID_FILE.write_text(str(os.getpid()))

    def handle_signal(signum, frame):
        print(f"\nreceived signal {signum}, stopping...")
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    client = HotspotClient(base_url=args.base_url)
    poller = AgentPoller(client, interval=args.interval)
    try:
        poller.run_forever()
    finally:
        PID_FILE.unlink(missing_ok=True)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop the running agent."""
    pid = _read_pid()
    if pid is None:
        print("agent not running (no pid file)")
        return 0
    if not _is_running(pid):
        print(f"pid file exists but process {pid} not running, removing stale pid file")
        PID_FILE.unlink(missing_ok=True)
        return 0
    print(f"stopping agent (pid={pid})")
    os.kill(pid, signal.SIGTERM)
    # wait up to 5s
    for _ in range(50):
        if not _is_running(pid):
            PID_FILE.unlink(missing_ok=True)
            print("stopped")
            return 0
        time.sleep(0.1)
    print("agent did not stop within 5s, sending SIGKILL")
    os.kill(pid, signal.SIGKILL)
    PID_FILE.unlink(missing_ok=True)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show current status."""
    pid = _read_pid()
    if pid is None:
        print("agent: stopped")
        return 0
    if not _is_running(pid):
        print(f"agent: stopped (stale pid file: {pid})")
        return 0
    print(f"agent: running (pid={pid})")
    # Optional: query backend for connection check
    if args.check:
        try:
            client = HotspotClient(base_url=args.base_url)
            tasks = client.get_tasks(limit=1)
            print(f"backend: connected ({args.base_url}), pending tasks visible")
        except Exception as e:
            print(f"backend: error - {e}")
            return 1
    return 0


def cmd_run_once(args: argparse.Namespace) -> int:
    """Run one polling cycle and exit. Useful for testing."""
    client = HotspotClient(base_url=args.base_url)
    tasks = client.get_tasks(limit=args.limit)
    print(f"fetched {len(tasks)} pending task(s)")
    success = 0
    failed = 0
    for task in tasks:
        print(f"  processing task {task['task_id']} ({task['task_type']})...")
        try:
            result = execute_task(task, client=client)
            client.complete_task(task["task_id"], "done", result=result)
            success += 1
            print(f"    ✓ done")
        except Exception as e:
            print(f"    ✗ failed: {e}")
            client.complete_task(task["task_id"], "failed", error=str(e))
            failed += 1
    print(f"summary: {success} success, {failed} failed")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="hotspot-agent",
        description="Hotspot Agent — pulls tasks from backend, executes skills, writes back",
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("HOTSPOT_API_BASE", "http://127.0.0.1:8000"),
        help="Backend base URL (default: HOTSPOT_API_BASE env or http://127.0.0.1:8000)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="Start poller (foreground)")
    p_start.add_argument("--interval", type=int, default=60, help="Polling interval seconds")

    p_stop = sub.add_parser("stop", help="Stop running poller")

    p_status = sub.add_parser("status", help="Show status")
    p_status.add_argument("--check", action="store_true", help="Also check backend connectivity")

    p_once = sub.add_parser("run-once", help="Run one cycle and exit")
    p_once.add_argument("--limit", type=int, default=5, help="Max tasks per cycle")

    args = parser.parse_args()
    handlers = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "run-once": cmd_run_once,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

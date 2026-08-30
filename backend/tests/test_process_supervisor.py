"""ProcessSupervisor 单元测试 — dsh 内置受管进程的宿主原语 (v0.6.3)。"""
from __future__ import annotations

import sys
import time

from backend.services.process_supervisor import ProcessSupervisor


def _sleep_command(seconds: float = 30) -> list[str]:
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


def _exit_command(rc: int = 1) -> list[str]:
    return [sys.executable, "-c", f"import sys; sys.exit({rc})"]


def test_start_and_status_running():
    sup = ProcessSupervisor()
    try:
        snap = sup.start("t1", _sleep_command())
        assert snap["running"] is True
        assert snap["pid"] is not None
        assert snap["uptime_s"] is not None
    finally:
        sup.stop("t1")


def test_start_idempotent_when_running():
    sup = ProcessSupervisor()
    try:
        first = sup.start("t2", _sleep_command())
        second = sup.start("t2", _sleep_command())
        assert first["pid"] == second["pid"]
    finally:
        sup.stop("t2")


def test_stop_returns_not_running():
    sup = ProcessSupervisor()
    sup.start("t3", _sleep_command())
    snap = sup.stop("t3")
    assert snap["running"] is False
    assert snap["stop_requested"] is True


def test_stop_when_never_started_is_safe():
    sup = ProcessSupervisor()
    snap = sup.stop("ghost")
    assert snap["running"] is False


def test_start_empty_command_reports_not_configured():
    sup = ProcessSupervisor()
    snap = sup.start("t4", [])
    assert snap["running"] is False
    assert snap["last_error"] == "command not configured"


def test_poll_auto_restarts_on_unexpected_exit():
    sup = ProcessSupervisor()
    sup.start("t5", _exit_command(rc=3))
    # 子进程退出需要一点时间
    time.sleep(0.5)
    snap = sup.poll("t5", command=_exit_command(rc=3))
    assert snap["restarts"] == 1
    # 重启成功 = 健康态 (start 清 last_error), 进程在跑
    assert snap["running"] is True


def test_poll_respects_stop_requested():
    sup = ProcessSupervisor()
    sup.start("t6", _sleep_command())
    sup.stop("t6")
    snap = sup.poll("t6", command=_sleep_command())
    assert snap["running"] is False
    assert snap["restarts"] == 0


def test_auto_restart_limit_reached():
    sup = ProcessSupervisor(max_restarts=1)
    sup.start("t7", _exit_command(rc=1))
    time.sleep(0.4)
    sup.poll("t7", command=_exit_command(rc=1))  # restart 1/1
    time.sleep(0.4)
    snap = sup.poll("t7", command=_exit_command(rc=1))  # 再退 → 超限
    time.sleep(0.2)
    assert "limit" in (snap["last_error"] or "") or snap["restarts"] == 1


def test_restart_relaunches_new_pid():
    sup = ProcessSupervisor()
    try:
        first = sup.start("t8", _sleep_command())
        second = sup.restart("t8")
        assert second["running"] is True
        assert second["pid"] != first["pid"]
    finally:
        sup.stop("t8")

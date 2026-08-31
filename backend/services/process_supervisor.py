"""进程监督器 — hotspot 内置受管子进程的统一宿主 (v0.6.3 dsh 内置化)。

三层架构裁决 (2026-08-24) 落地件: dsh (认知大脑) / pi (执行 agent) 等
外部运行时由 hotspot 以**受管子进程**方式内置, 不再依赖用户手工在外部
拉起。本模块提供与具体业务无关的生命周期原语:

- ``start(name, command, ...)``  幂等启动 (已运行则返回现状)
- ``stop(name, timeout)``        终止 (terminate → 超时 kill)
- ``restart(name)``              重启
- ``status(name)``               状态快照 (running/pid/uptime/restarts/last_error)
- ``poll(name)``                 意外退出检测 + 有限自动重启

设计约束:
- 单进程内 registry (dict), 与 hotspot 单进程架构一致; 不引入外部依赖
- spawn 使用 ``subprocess.Popen``, stdout/stderr 落 PIPE 并由后台线程
  消费 (防管道阻塞), 保留尾部日志供排障
- 自动重启策略: 仅对**非用户主动 stop** 的意外退出生效, 次数上限
  ``max_restarts`` (默认 3), 超限后标记 last_error 等待人工介入
"""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.logging_config import logger
from backend.observability_records import record_process_event

_MAX_TAIL_LINES = 50


@dataclass
class ManagedProcess:
    """一个受管子进程的运行时状态。"""

    name: str
    command: list[str]
    cwd: str | None = None
    env: dict[str, str] | None = None
    popen: subprocess.Popen | None = None
    started_at: float | None = None          # time.monotonic()
    started_at_iso: str | None = None
    restarts: int = 0
    stop_requested: bool = False             # 用户主动 stop → 不自动重启
    last_error: str | None = None
    log_tail: list[str] = field(default_factory=list)

    def snapshot(self) -> dict:
        running = self.popen is not None and self.popen.poll() is None
        return {
            "name": self.name,
            "running": running,
            "pid": self.popen.pid if self.popen and running else None,
            "uptime_s": (
                round(time.monotonic() - self.started_at, 1)
                if running and self.started_at is not None else None
            ),
            "restarts": self.restarts,
            "stop_requested": self.stop_requested,
            "last_error": self.last_error,
            "command": self.command,
            "started_at": self.started_at_iso,
            "log_tail": list(self.log_tail[-10:]),
        }


class ProcessSupervisor:
    """受管子进程注册表。实例挂在 app.state 或模块级均可 (线程安全)。"""

    def __init__(self, max_restarts: int = 3) -> None:
        self._procs: dict[str, ManagedProcess] = {}
        self._lock = threading.Lock()
        self._max_restarts = max_restarts

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self, name: str, command: list[str], *, cwd: str | None = None,
              env: dict[str, str] | None = None) -> dict:
        """启动受管进程。幂等: 已在运行则直接返回快照。"""
        with self._lock:
            existing = self._procs.get(name)
            if existing and existing.popen and existing.popen.poll() is None:
                return existing.snapshot()

            if not command:
                mp = existing or ManagedProcess(name=name, command=[])
                mp.last_error = "command not configured"
                self._procs[name] = mp
                record_process_event(name=name, event="spawn", detail="command not configured")
                return mp.snapshot()

            mp = existing or ManagedProcess(name=name, command=command)
            mp.command = command
            mp.cwd = cwd
            mp.env = env
            mp.stop_requested = False
            try:
                mp.popen = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except OSError as e:
                mp.last_error = f"spawn failed: {e}"
                mp.popen = None
                logger.warning("supervisor spawn %s failed: %s", name, e)
                record_process_event(
                    name=name, event="crash",
                    detail=f"spawn failed: {e}",
                )
                self._procs[name] = mp
                return mp.snapshot()

            mp.started_at = time.monotonic()
            mp.started_at_iso = datetime.now(timezone.utc).isoformat()
            mp.last_error = None
            mp.log_tail = []
            threading.Thread(
                target=self._drain_output, args=(mp,), daemon=True, name=f"sup-{name}",
            ).start()
            logger.info("supervisor started %s: %s", name, " ".join(command))
            record_process_event(
                name=name, event="spawn",
                pid=mp.popen.pid,
                detail=f"command={' '.join(command)[:200]}",
            )
            self._procs[name] = mp
            return mp.snapshot()

    def stop(self, name: str, timeout: float = 10.0) -> dict:
        """终止进程 (terminate → 超时 kill)。未运行时静默返回。"""
        with self._lock:
            mp = self._procs.get(name)
            if mp is None or mp.popen is None:
                empty = ManagedProcess(name=name, command=mp.command if mp else [])
                empty.stop_requested = True
                self._procs[name] = empty
                return empty.snapshot()

            mp.stop_requested = True
            try:
                mp.popen.terminate()
                mp.popen.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                mp.popen.kill()
                mp.popen.wait(timeout=5)
            except OSError as e:
                mp.last_error = f"stop failed: {e}"
            mp.started_at = None
            logger.info("supervisor stopped %s", name)
            record_process_event(
                name=name, event="exit",
                pid=mp.popen.pid if mp.popen else None,
                exit_code=mp.popen.returncode if mp.popen else None,
                detail="stop_requested",
            )
            return mp.snapshot()

    def restart(self, name: str, *, command: list[str] | None = None,
                cwd: str | None = None, env: dict[str, str] | None = None) -> dict:
        """重启: stop 后以新/旧配置 start。"""
        with self._lock:
            mp = self._procs.get(name)
        if mp is not None:
            self.stop(name)
            command = command or mp.command
            cwd = cwd if cwd is not None else mp.cwd
            env = env if env is not None else mp.env
            if not command:
                return self.status(name)
        elif command is None:
            return self.status(name)
        return self.start(name, command, cwd=cwd, env=env)

    # ------------------------------------------------------------------
    # 观测
    # ------------------------------------------------------------------
    def status(self, name: str) -> dict:
        with self._lock:
            mp = self._procs.get(name)
        if mp is None:
            return {"name": name, "running": False, "pid": None, "uptime_s": None,
                    "restarts": 0, "stop_requested": False, "last_error": None,
                    "command": [], "started_at": None, "log_tail": []}
        return mp.snapshot()

    def poll(self, name: str, *, command: list[str] | None = None,
             cwd: str | None = None, env: dict[str, str] | None = None) -> dict:
        """意外退出检测 + 有限自动重启。

        轮询方 (前端状态栏 / health 端点) 周期调用; 用户主动 stop 的进程
        不复活。重启配置取最近一次 start 的参数 (可显式覆盖)。
        """
        with self._lock:
            mp = self._procs.get(name)
        if mp is None or mp.popen is None:
            return self.status(name)
        if mp.popen.poll() is None:
            return mp.snapshot()  # 仍在运行

        rc = mp.popen.returncode
        if mp.stop_requested:
            return mp.snapshot()  # 主动停止, 不复活

        if mp.restarts >= self._max_restarts:
            mp.last_error = f"exited rc={rc}; auto-restart limit ({self._max_restarts}) reached"
            logger.warning("supervisor %s: %s", name, mp.last_error)
            record_process_event(
                name=name, event="crash",
                pid=mp.popen.pid if mp.popen else None,
                uptime_s=round(time.monotonic() - mp.started_at, 1)
                    if mp.started_at else None,
                exit_code=rc,
                detail=mp.last_error,
            )
            return mp.snapshot()

        mp.restarts += 1
        mp.last_error = f"exited rc={rc}; auto-restarting ({mp.restarts}/{self._max_restarts})"
        logger.warning("supervisor %s exited rc=%s; restart %s/%s",
                       name, rc, mp.restarts, self._max_restarts)
        record_process_event(
            name=name, event="exit",
            pid=mp.popen.pid if mp.popen else None,
            uptime_s=round(time.monotonic() - mp.started_at, 1)
                if mp.started_at else None,
            exit_code=rc,
            detail=mp.last_error,
        )
        return self.restart(name, command=command or mp.command,
                            cwd=cwd, env=env)

    # ------------------------------------------------------------------
    def _drain_output(self, mp: ManagedProcess) -> None:
        """消费子进程 stdout/stderr, 保留尾部日志防管道阻塞。"""
        proc = mp.popen
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                mp.log_tail.append(line.rstrip()[:500])
                if len(mp.log_tail) > _MAX_TAIL_LINES:
                    mp.log_tail = mp.log_tail[-_MAX_TAIL_LINES:]
        except (OSError, ValueError):
            pass


__all__ = ["ManagedProcess", "ProcessSupervisor"]

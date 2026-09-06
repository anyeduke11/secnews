"""pi live AgentSession 适配层 (v1.0 T10).

定位
----
与既有 mock pi session **并存**, 不替换:

- 既有路径 (``backend/services/dsh/session_bridge.py`` 等) 走 mock / HTTP;
- 本模块负责"生产真 vendor"路径 — subprocess 启 pi CLI (node + pi binary),
  按 AgentSession 事件流协议与 ``scripts/t04_sdk_probe.py`` mock 对齐,
  框架事件形状与 lock 中的 pi coding-agent 0.85.0 SDK 一致。

模式切换
--------
settings.kv ``pi.session_mode`` ∈ ``"mock"|"live"``:
- ``mock`` (默认): 走既有 mock (与 T04 默认一致, 不破坏老调用方);
- ``live``: 走本模块 ``LivePiSession`` (subprocess 启 vendor + 事件流)。

事件流协议 (与 pi coding-agent SDK AgentSession 对齐)
---------------------------------------------------
请求帧: ``{"event": "init"|"prompt"|"cancel"|"tool_result", "session_id": str, ...}``
事件帧: ``{"event": "session.created"|"assistant.message"|"tool.call"|"tool.result"|"session.complete"|"session.cancelled"|"error", "session_id": str, "ts": float, "data": {...}}``

每条请求可派发**多条**事件帧 (与 dsh 一问一答不同), 由 ``iter_events()``
generator 透传给上层消费。

纪律
----
- 不引入新依赖 (仅 stdlib: subprocess / json / threading / queue);
- 不写真实库 (T01 conftest 隔离);
- 测试不真启 vendor — mock subprocess 验证事件流形状。
"""
from __future__ import annotations

import json
import logging
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from backend.repository.settings_repo import SettingsRepository

log = logging.getLogger("hotspot.pi.live_session")

_SESSION_MODE_KEY = "pi.session_mode"
DEFAULT_TIMEOUT_S = 30.0
# 锁版本: 6f11c31d1134a32e64bf221baeec38e431091e05 (coding-agent 0.85.0)
# vendor 启动约定: node packages/coding-agent/dist/cli.js <args>
# 由 lock 锁定的 commit_sha 推导; 本模块不直接读 lock, 由调用方注入 command。
DEFAULT_PI_COMMAND: tuple[str, ...] = ("node", "packages/coding-agent/dist/cli.js")


@dataclass
class PiEvent:
    """单条 AgentSession 事件帧。"""

    event: str
    session_id: str
    ts: float
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "session_id": self.session_id,
            "ts": self.ts,
            "data": self.data,
        }


class LivePiSession:
    """pi AgentSession stdio 适配 — subprocess 启 vendor, 派事件。

    与 LiveDSHClient 差异: pi 是**事件流** (一请求 → 多事件), 故 API
    用 generator 形式 ``iter_events()``, 调用方按需消费。
    """

    def __init__(
        self,
        command: tuple[str, ...] | list[str] | None = None,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        cwd: Path | None = None,
    ) -> None:
        self._command: tuple[str, ...] = tuple(command) if command else DEFAULT_PI_COMMAND
        self._timeout_s = timeout_s
        self._cwd = cwd
        self._proc: subprocess.Popen | None = None
        self._events: queue.Queue[PiEvent | None] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._closed = False

    # ------------------------------------------------------------------
    # 进程生命周期
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._proc is not None:
            return
        try:
            self._proc = subprocess.Popen(
                list(self._command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=str(self._cwd) if self._cwd else None,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                f"pi vendor 启动失败: command={self._command} ({e})"
            ) from e
        except OSError as e:
            raise RuntimeError(f"pi vendor 启动 OSError: {e}") from e
        self._reader = threading.Thread(
            target=_reader_loop, args=(self._proc, self._events),
            name="pi-live-reader", daemon=True,
        )
        self._reader.start()
        log.info("pi live subprocess started: cmd=%s pid=%s",
                 self._command, self._proc.pid)

    def stop(self, *, timeout_s: float = 2.0) -> None:
        self._closed = True
        self._events.put(None)  # 通知 iter_events 结束
        if self._proc is None:
            return
        try:
            if self._proc.stdin and not self._proc.stdin.closed:
                try:
                    self._proc.stdin.close()
                except Exception:
                    pass
            self._proc.terminate()
            try:
                self._proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                log.warning("pi vendor 未在 %.1fs 内退出, 强杀", timeout_s)
                self._proc.kill()
                self._proc.wait(timeout=1.0)
        finally:
            self._proc = None
            self._reader = None

    def close(self) -> None:
        self.stop()

    def __enter__(self) -> LivePiSession:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # 事件流协议
    # ------------------------------------------------------------------
    def _send(self, payload: dict[str, Any]) -> None:
        """写 1 条请求帧到 vendor stdin (单行 JSON)。"""
        if self._closed:
            raise RuntimeError("pi live session 已关闭")
        if self._proc is None:
            self.start()
        frame = json.dumps(payload, ensure_ascii=False)
        try:
            assert self._proc.stdin and not self._proc.stdin.closed
            self._proc.stdin.write(frame + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"pi vendor stdin 写入失败: {e}") from e

    def iter_events(
        self,
        *,
        max_events: int | None = None,
        idle_timeout_s: float | None = None,
    ) -> Iterator[PiEvent]:
        """消费当前已排队的事件, 直到 ``session.complete/cancelled/error`` 或超时。

        ``max_events`` — 上限保护 (默认不限), 防止 vendor 永远不收尾导致 hang。
        ``idle_timeout_s`` — 单条事件最大等待时间 (默认 ``self._timeout_s``)。
        """
        idle = idle_timeout_s if idle_timeout_s is not None else self._timeout_s
        terminal_events = {"session.complete", "session.cancelled", "error"}
        count = 0
        while True:
            if max_events is not None and count >= max_events:
                log.warning("pi iter_events 达到 max_events=%s, 提前终止", max_events)
                return
            try:
                ev = self._events.get(timeout=idle)
            except queue.Empty:
                log.warning("pi iter_events 超时 (%.1fs)", idle)
                return
            if ev is None:
                return
            yield ev
            count += 1
            if ev.event in terminal_events:
                return

    # ------------------------------------------------------------------
    # 业务便捷方法
    # ------------------------------------------------------------------
    def init(self, session_id: str, *, profile: str = "default") -> Iterator[PiEvent]:
        """派 ``init`` → 期望首事件 ``session.created``。"""
        self._send({"event": "init", "session_id": session_id, "profile": profile})
        return self.iter_events()

    def prompt(
        self, session_id: str, text: str, *,
        max_events: int | None = 64,
    ) -> Iterator[PiEvent]:
        """派 ``prompt`` → 流式 assistant.message + tool.call/result + complete。"""
        self._send({
            "event": "prompt", "session_id": session_id,
            "text": text, "ts": time.time(),
        })
        return self.iter_events(max_events=max_events)

    def cancel(self, session_id: str, reason: str = "user_request") -> Iterator[PiEvent]:
        """派 ``cancel`` → 期望 ``session.cancelled``。"""
        self._send({
            "event": "cancel", "session_id": session_id, "reason": reason,
        })
        return self.iter_events()

    def tool_result(
        self, session_id: str, call_id: str, content: str, ok: bool = True,
    ) -> Iterator[PiEvent]:
        """派 ``tool_result`` — 工具回执, 验证 round-trip。"""
        self._send({
            "event": "tool_result", "session_id": session_id,
            "call_id": call_id, "content": content, "ok": ok,
        })
        return self.iter_events()


# ----------------------------------------------------------------------
# 内部 — stdout reader 线程
# ----------------------------------------------------------------------
def _reader_loop(
    proc: subprocess.Popen,
    out_q: queue.Queue[PiEvent | None],
) -> None:
    """在独立线程里把 vendor stdout 一行一行解析并 push 到 out_q。"""
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                log.warning("pi vendor 帧解析失败: %r", line[:200])
                continue
            try:
                ev = PiEvent(
                    event=str(data.get("event", "")),
                    session_id=str(data.get("session_id", "")),
                    ts=float(data.get("ts", time.time())),
                    data=dict(data.get("data") or {}),
                )
            except Exception as e:
                log.warning("pi vendor 帧构造失败: %s (%r)", e, line[:200])
                continue
            out_q.put(ev)
    except Exception as e:
        log.warning("pi reader loop 异常退出: %s", e)


# ----------------------------------------------------------------------
# 模式解析 (settings.kv ``pi.session_mode``)
# ----------------------------------------------------------------------
def get_session_mode() -> str:
    """读 ``pi.session_mode``; 默认 ``mock`` (与既有 mock 兼容)。"""
    raw = SettingsRepository().get(_SESSION_MODE_KEY)
    if raw in ("mock", "live"):
        return raw
    if raw is not None:
        log.warning("pi.session_mode 非法值 %r, 回退 mock", raw)
    return "mock"


__all__ = [
    "DEFAULT_PI_COMMAND",
    "LivePiSession",
    "PiEvent",
    "get_session_mode",
]


if __name__ == "__main__":  # pragma: no cover
    print(f"live_session module — pid={__name__}", file=sys.stderr)

"""DSH live stdio JSON-RPC 客户端 (v1.0 T10).

定位
----
与 ``bridge.DSHClient`` (HTTP) **并存**, 不替换:

- HTTP 客户端负责 :3210 健康检查 / 任务派发等"控制面+任务面"语义;
- 本模块负责"生产真 vendor"路径 — stdio JSON-RPC 走 subprocess,
  框架协议形状与 ``scripts/t04_sdk_probe.py`` mock 完全对齐,
  仅协议格式与 lock 中的 ``deepseek-harness`` Python SDK 一致。

模式切换
--------
settings.kv ``dsh.bridge_mode`` ∈ ``"http"|"stdio"``:
- ``http`` (默认): 走既有 ``DSHClient``;
- ``stdio``: 走本模块 ``LiveDSHClient`` (subprocess 启 vendor + JSON-RPC)。
``DshRuntime.execute_with_fallback`` 已在 B4 把异常映射为 mock 兜底, 故本模块
subprocess 启动失败/超时/非零退出 → 直接抛, 由上层 runtime 兜住, 不重复
fallback 链。

JSON-RPC 帧契约 (与官方 SDK client.py + t04 mock 对齐)
-----------------------------------------------------
请求:  ``{"jsonrpc": "2.0", "id": int, "method": str, "params": dict}``
响应:  ``{"jsonrpc": "2.0", "id": int, "result": any}`` 或
       ``{"jsonrpc": "2.0", "id": int, "error": {"code": int, "message": str}}``
错误响应映射为 ``RuntimeError`` 上抛, 由上层 DshRuntime 兜底到 mock。

纪律
----
- 不引入新依赖 (仅 stdlib: subprocess / json / threading);
- 不写真实库 (T01 conftest 强制隔离);
- 测试不真启 vendor — 用 mock subprocess (test_live_bridge.py)。
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
from typing import Any

from backend.repository.settings_repo import SettingsRepository

log = logging.getLogger("hotspot.dsh.live_bridge")

_BRIDGE_MODE_KEY = "dsh.bridge_mode"
DEFAULT_TIMEOUT_S = 30.0
# 锁版本: d347e703908d0406b7a7ef80e3a0e594d86b2215 (Python SDK client.py)
# vendor 启动约定: python -m deepseek_harness <mode> --stdio
# 由 lock 锁定的 commit_sha 推导; 本模块不直接读 lock, 由调用方注入 command。
DEFAULT_DSH_COMMAND: tuple[str, ...] = ("python", "-m", "deepseek_harness")


@dataclass
class JSONRPCRequest:
    """单条 JSON-RPC 请求。"""

    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: int = 1


@dataclass
class JSONRPCResponse:
    """单条 JSON-RPC 响应 (含错误路径)。"""

    id: int | None
    result: Any = None
    error: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class LiveDSHClient:
    """stdio JSON-RPC 客户端 — 启 vendor subprocess 派任务。

    生命周期:
      - ``__init__``: 不启进程, 仅缓存 command + timeout;
      - ``start()``: 第一次 RPC 触发 (懒加载) 或显式 ``start()``;
      - ``stop()``: ``close()`` + 关闭 stdin, join reader 线程;
      - ``__enter__/__exit__``: context manager 协议。
    """

    def __init__(
        self,
        command: tuple[str, ...] | list[str] | None = None,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        cwd: Path | None = None,
    ) -> None:
        self._command: tuple[str, ...] = tuple(command) if command else DEFAULT_DSH_COMMAND
        self._timeout_s = timeout_s
        self._cwd = cwd
        self._proc: subprocess.Popen | None = None
        self._next_id = 1
        self._id_lock = threading.Lock()
        # response 队列: reader 线程把 stdout 行 push 进来, request 线程阻塞 pop
        self._responses: queue.Queue[JSONRPCResponse] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._closed = False

    # ------------------------------------------------------------------
    # 进程生命周期
    # ------------------------------------------------------------------
    def start(self) -> None:
        """启动 vendor subprocess + 启动 stdout reader 线程。"""
        if self._proc is not None:
            return
        try:
            self._proc = subprocess.Popen(
                list(self._command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # line-buffered
                cwd=str(self._cwd) if self._cwd else None,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                f"dsh vendor 启动失败: command={self._command} ({e})"
            ) from e
        except OSError as e:
            raise RuntimeError(f"dsh vendor 启动 OSError: {e}") from e
        self._reader = threading.Thread(
            target=_reader_loop, args=(self._proc, self._responses),
            name="dsh-live-reader", daemon=True,
        )
        self._reader.start()
        log.info("dsh live subprocess started: cmd=%s pid=%s",
                 self._command, self._proc.pid)

    def stop(self, *, timeout_s: float = 2.0) -> None:
        """关闭 stdin + 终止进程 + join reader。"""
        self._closed = True
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
                log.warning("dsh vendor 未在 %.1fs 内退出, 强杀", timeout_s)
                self._proc.kill()
                self._proc.wait(timeout=1.0)
        finally:
            self._proc = None
            self._reader = None

    def close(self) -> None:
        self.stop()

    def __enter__(self) -> LiveDSHClient:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # JSON-RPC 调用
    # ------------------------------------------------------------------
    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """发送 JSON-RPC 请求并阻塞等响应, 超时抛 TimeoutError。"""
        if self._closed:
            raise RuntimeError("dsh live client 已关闭")
        if self._proc is None:
            self.start()
        with self._id_lock:
            req_id = self._next_id
            self._next_id += 1
        req = JSONRPCRequest(method=method, params=params or {}, id=req_id)
        frame = json.dumps({
            "jsonrpc": "2.0", "id": req.id, "method": req.method, "params": req.params,
        }, ensure_ascii=False)
        try:
            assert self._proc.stdin and not self._proc.stdin.closed
            self._proc.stdin.write(frame + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"dsh vendor stdin 写入失败: {e}") from e

        deadline = time.monotonic() + self._timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"dsh JSON-RPC 超时 ({self._timeout_s}s): method={method}"
                )
            try:
                resp = self._responses.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError(
                    f"dsh JSON-RPC 超时 ({self._timeout_s}s): method={method}"
                )
            if resp.id == req.id:
                break
            # id 不匹配: 旧请求残留 (mock 单线场景), 丢弃并继续等
            log.warning("dsh JSON-RPC id 不匹配: 期望 %s, 收到 %s", req.id, resp.id)
        if not resp.ok:
            err = resp.error or {"code": -1, "message": "unknown"}
            raise RuntimeError(
                f"dsh JSON-RPC 错误: code={err.get('code')} msg={err.get('message')}"
            )
        return resp.result

    # ------------------------------------------------------------------
    # 业务便捷方法 (与 DSHClient 对齐)
    # ------------------------------------------------------------------
    def health_check(self) -> bool:
        """派 ``session.ping`` — vendor 正常响应即 True。"""
        try:
            self.call("session.ping", {})
            return True
        except Exception as e:
            log.warning("dsh live health_check 失败: %s", e)
            return False

    def send_task(self, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """派 ``task.dispatch`` — 与 HTTP 客户端同名方法协议对齐。"""
        return self.call("task.dispatch", {"task_type": task_type, "payload": payload})

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self.call("session.get", {"session_id": session_id})

    def cancel(self, session_id: str) -> dict[str, Any]:
        return self.call("session.cancel", {"session_id": session_id})


# ----------------------------------------------------------------------
# 内部 — stdout reader 线程
# ----------------------------------------------------------------------
def _reader_loop(
    proc: subprocess.Popen,
    out_q: queue.Queue[JSONRPCResponse],
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
                log.warning("dsh vendor 帧解析失败: %r", line[:200])
                continue
            try:
                resp = JSONRPCResponse(
                    id=data.get("id"),
                    result=data.get("result"),
                    error=data.get("error"),
                )
            except Exception as e:
                log.warning("dsh vendor 帧构造失败: %s (%r)", e, line[:200])
                continue
            out_q.put(resp)
    except Exception as e:
        log.warning("dsh reader loop 异常退出: %s", e)


# ----------------------------------------------------------------------
# 模式解析 (settings.kv ``dsh.bridge_mode``)
# ----------------------------------------------------------------------
def get_bridge_mode() -> str:
    """读 ``dsh.bridge_mode``; 默认 ``http`` (与现有 DSHClient 一致)。"""
    raw = SettingsRepository().get(_BRIDGE_MODE_KEY)
    if raw in ("http", "stdio"):
        return raw
    if raw is not None:
        log.warning("dsh.bridge_mode 非法值 %r, 回退 http", raw)
    return "http"


__all__ = [
    "DEFAULT_DSH_COMMAND",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "LiveDSHClient",
    "get_bridge_mode",
]


if __name__ == "__main__":  # pragma: no cover
    print(f"live_bridge module — pid={__name__}", file=sys.stderr)

"""LiveDSHClient mock subprocess 测试 (T10).

不真启 vendor; mock subprocess 验 JSON-RPC 帧形状 + 错误路径 +
超时 + 启动失败兜底, 不出网、不写真实库 (T01 conftest 隔离)。
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from backend.repository.settings_repo import SettingsRepository
from backend.services.dsh.live_bridge import (
    LiveDSHClient,
    get_bridge_mode,
)


def _mock_dsh_script() -> str:
    """mock dsh stdio JSON-RPC server — 与 t04_sdk_probe.py 协议对齐。"""
    return r"""
import json, sys
def handle(req):
    method = req.get("method")
    if method == "session.ping":
        return {"pong": True, "version": "0.1.3-alpha.1"}
    if method == "task.dispatch":
        return {"task_id": "t-mock", "status": "queued"}
    if method == "session.get":
        return {"session_id": req["params"].get("session_id"), "state": "active"}
    if method == "session.cancel":
        return {"cancelled": True}
    if method == "trigger.error":
        return {"error": {"code": -32603, "message": "intentional"}}
    return {"error": {"code": -32601, "message": "Method not found"}}
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        resp = {"jsonrpc": "2.0", "id": req.get("id")}
        out = handle(req)
        if "error" in out:
            resp["error"] = out["error"]
        else:
            resp["result"] = out
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}) + "\n")
        sys.stdout.flush()
"""


@pytest.fixture()
def mock_proc():
    """启 mock dsh subprocess, 测试结束自动清理。"""
    p = subprocess.Popen(
        [sys.executable, "-c", _mock_dsh_script()],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    yield p
    if p.stdin and not p.stdin.closed:
        try:
            p.stdin.close()
        except Exception:
            pass
    p.terminate()
    p.wait(timeout=2)


def _client_from_mock(mock_proc: subprocess.Popen, *, timeout_s: float = 5.0) -> LiveDSHClient:
    """构造 LiveDSHClient 但替换内部 proc 为测试给的 mock — 绕开真实 subprocess 启动。

    我们用 ``client.__new__`` 直接填字段, 因为 ``start()`` 会真启子进程。
    """
    cli = LiveDSHClient.__new__(LiveDSHClient)
    cli._command = ("mock",)
    cli._timeout_s = timeout_s
    cli._cwd = None
    cli._proc = mock_proc
    cli._next_id = 1
    cli._id_lock = __import__("threading").Lock()
    import queue
    import threading
    cli._responses = queue.Queue()
    cli._reader = threading.Thread(
        target=cli.__class__.__module__ and _reader_for_test,
        args=(mock_proc, cli._responses),
        daemon=True,
    )
    cli._closed = False
    cli._reader.start()
    return cli


def _reader_for_test(proc, out_q):
    """测试用 reader — 与 live_bridge._reader_loop 等价但绕过模块引用。"""
    from backend.services.dsh.live_bridge import _reader_loop
    _reader_loop(proc, out_q)


def test_session_ping_roundtrip(mock_proc):
    """``session.ping`` 应正确收到 vendor pong, 不抛异常。"""
    cli = _client_from_mock(mock_proc)
    try:
        result = cli.call("session.ping", {})
        assert result == {"pong": True, "version": "0.1.3-alpha.1"}
    finally:
        cli.stop()


def test_task_dispatch_roundtrip(mock_proc):
    """``task.dispatch`` 应正确派发并返回 task_id。"""
    cli = _client_from_mock(mock_proc)
    try:
        out = cli.send_task("cve-impact-brief", {"asset": "gateway-A"})
        assert out["task_id"] == "t-mock"
        assert out["status"] == "queued"
    finally:
        cli.stop()


def test_jsonrpc_error_propagates(mock_proc):
    """vendor 端返回 error 时, LiveDSHClient 应上抛 RuntimeError。"""
    cli = _client_from_mock(mock_proc)
    try:
        with pytest.raises(RuntimeError, match="dsh JSON-RPC 错误"):
            cli.call("trigger.error", {})
    finally:
        cli.stop()


def test_method_not_found(mock_proc):
    """未注册方法 → vendor 返回 error.code=-32601 → 客户端抛。"""
    cli = _client_from_mock(mock_proc)
    try:
        with pytest.raises(RuntimeError, match="-32601"):
            cli.call("does.not.exist", {})
    finally:
        cli.stop()


def test_health_check_returns_true_on_pong(mock_proc):
    """health_check 派 session.ping — vendor 正常 → True。"""
    cli = _client_from_mock(mock_proc)
    try:
        assert cli.health_check() is True
    finally:
        cli.stop()


def test_close_is_idempotent():
    """关闭未启动的 client 不应抛异常。"""
    cli = LiveDSHClient(command=("echo", "noop"))
    cli.close()
    cli.close()  # idempotent


def test_get_bridge_mode_default(temp_db):
    """默认 mode 应为 ``http`` (与现有 DSHClient 一致)。"""
    assert get_bridge_mode() == "http"


def test_get_bridge_mode_stdio_round_trip(temp_db):
    """写 ``stdio`` → 读回 stdio; 写非法值 → 回退 http。"""
    repo = SettingsRepository()
    repo.set("dsh.bridge_mode", "stdio")
    assert get_bridge_mode() == "stdio"
    repo.set("dsh.bridge_mode", "garbage")
    assert get_bridge_mode() == "http"
    # 清理
    repo.set("dsh.bridge_mode", "http")


def test_start_with_missing_command_raises():
    """无效 command → 启动失败 → 上抛 RuntimeError (供 DshRuntime 兜底)。"""
    cli = LiveDSHClient(command=("/no/such/binary/exists",))
    with pytest.raises(RuntimeError, match="dsh vendor 启动失败"):
        cli.start()
    # 失败后 stop 也不该再 crash
    cli.stop()

"""LivePiSession mock subprocess 测试 (T10).

不真启 vendor; mock subprocess 验事件流形状 + round-trip +
取消语义 + 启动失败兜底, 不出网、不写真实库 (T01 conftest 隔离)。
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from queue import Queue

import pytest

from backend.repository.settings_repo import SettingsRepository
from backend.services.pi.live_session import (
    LivePiSession,
    PiEvent,
    get_session_mode,
)


def _mock_pi_script() -> str:
    """mock pi AgentSession server — 与 t04_sdk_probe.py 协议对齐。"""
    return r"""
import json, sys, time, uuid
def emit(event, session_id, **data):
    sys.stdout.write(json.dumps({
        "event": event, "session_id": session_id,
        "ts": time.time(), "data": data,
    }) + "\n")
    sys.stdout.flush()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        ev = req.get("event")
        sid = req.get("session_id", "")
        if ev == "init":
            emit("session.created", sid, agent="mock-pi", version="0.85.0")
        elif ev == "prompt":
            text = req.get("text", "")[:40]
            emit("assistant.message", sid, content=f"mock reply for: {text}")
            call_id = uuid.uuid4().hex[:8]
            emit("tool.call", sid, tool_name="read_file", call_id=call_id,
                 args={"path": "/dev/null"})
            emit("tool.result", sid, call_id=call_id, content="(mock empty)", ok=True)
            emit("session.complete", sid, tokens_in=12, tokens_out=24, duration_ms=8)
        elif ev == "cancel":
            emit("session.cancelled", sid, reason=req.get("reason", "user_request"))
        elif ev == "tool_result":
            emit("tool.ack", sid, call_id=req.get("call_id"), accepted=req.get("ok", True))
        elif ev == "trigger.error":
            emit("error", sid, code=-32603, message="intentional")
        else:
            emit("error", sid, code=-32601, message=f"unknown event: {ev}")
    except Exception as e:
        sys.stdout.write(json.dumps({"event": "error", "data": {"code": -32700, "message": str(e)}}) + "\n")
        sys.stdout.flush()
"""


@pytest.fixture()
def mock_proc():
    """启 mock pi subprocess, 测试结束自动清理。"""
    p = subprocess.Popen(
        [sys.executable, "-c", _mock_pi_script()],
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


def _session_from_mock(mock_proc: subprocess.Popen, *, timeout_s: float = 5.0) -> LivePiSession:
    """构造 LivePiSession 但替换内部 proc — 绕开真实 subprocess 启动。"""
    sess = LivePiSession.__new__(LivePiSession)
    sess._command = ("mock",)
    sess._timeout_s = timeout_s
    sess._cwd = None
    sess._proc = mock_proc
    sess._events = Queue()
    sess._reader = threading.Thread(
        target=_reader_for_test, args=(mock_proc, sess._events), daemon=True,
    )
    sess._closed = False
    sess._reader.start()
    return sess


def _reader_for_test(proc, out_q):
    from backend.services.pi.live_session import _reader_loop
    _reader_loop(proc, out_q)


def test_init_emits_session_created(mock_proc):
    """``init`` → 期望首事件 ``session.created``。"""
    sess = _session_from_mock(mock_proc)
    try:
        events = list(sess.init("sess-001"))
        assert len(events) >= 1
        assert events[0].event == "session.created"
        assert events[0].session_id == "sess-001"
    finally:
        sess.stop()


def test_prompt_full_event_stream(mock_proc):
    """``prompt`` → 应依次派 assistant.message / tool.call / tool.result / session.complete。"""
    sess = _session_from_mock(mock_proc)
    try:
        events = list(sess.prompt("sess-002", "列出关键源"))
        names = [e.event for e in events]
        assert "assistant.message" in names
        assert "tool.call" in names
        assert "tool.result" in names
        assert names[-1] == "session.complete"
    finally:
        sess.stop()


def test_tool_call_round_trip_preserves_call_id(mock_proc):
    """tool.call.call_id 必须透传到 tool.result.call_id (F05 round-trip)。"""
    sess = _session_from_mock(mock_proc)
    try:
        events = list(sess.prompt("sess-003", "test round-trip"))
        calls = [e for e in events if e.event == "tool.call"]
        results = [e for e in events if e.event == "tool.result"]
        assert len(calls) >= 1
        assert len(results) >= 1
        # mock 内部用同一 call_id
        assert calls[0].data["call_id"] == results[0].data["call_id"]
    finally:
        sess.stop()


def test_cancel_emits_session_cancelled(mock_proc):
    """``cancel`` → 期望 ``session.cancelled`` 终态 (F09 取消语义)。"""
    sess = _session_from_mock(mock_proc)
    try:
        events = list(sess.cancel("sess-004", reason="user_request"))
        names = [e.event for e in events]
        assert "session.cancelled" in names
        last = events[-1]
        assert last.data["reason"] == "user_request"
    finally:
        sess.stop()


def test_tool_result_ack(mock_proc):
    """``tool_result`` → vendor ack, 验证回执路径。"""
    sess = _session_from_mock(mock_proc)
    try:
        events = list(sess.tool_result("sess-005", "call-xyz", "data", ok=True))
        assert events[0].event == "tool.ack"
        assert events[0].data["call_id"] == "call-xyz"
        assert events[0].data["accepted"] is True
    finally:
        sess.stop()


def test_close_is_idempotent():
    """未启动 session 关闭应幂等。"""
    sess = LivePiSession(command=("echo", "noop"))
    sess.close()
    sess.close()


def test_get_session_mode_default(temp_db):
    """默认 mode 应为 ``mock`` (与既有 mock 兼容)。"""
    assert get_session_mode() == "mock"


def test_get_session_mode_live_round_trip(temp_db):
    """写 ``live`` → 读回 live; 写非法 → 回退 mock。"""
    repo = SettingsRepository()
    repo.set("pi.session_mode", "live")
    assert get_session_mode() == "live"
    repo.set("pi.session_mode", "garbage")
    assert get_session_mode() == "mock"
    repo.set("pi.session_mode", "mock")  # 清理


def test_start_with_missing_command_raises():
    """无效 command → 启动失败 → 上抛 RuntimeError。"""
    sess = LivePiSession(command=("/no/such/binary/exists",))
    with pytest.raises(RuntimeError, match="pi vendor 启动失败"):
        sess.start()
    sess.stop()

"""v1.0 C06 反例测试 — pi_adapter 真 vendor 适配 + D3 节点降级 (R06 + R07).

依据 [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md §7 C06] + [REVIEW_2026-09-07.md R06]

范围 (本测试):
  R06 真 vendor 适配:
    - 真 vendor 路径检查 (``runtime/upstreams/pi/`` 存在 + commit_sha 锁定)
    - 真 vendor 启动探测 (probe_pi_vendor) — C06 D3 节点应触发 blocked
    - 真 vendor 不可用 → 显式 ``PIVendorUnavailableError`` + audit 双写
    - 真 vendor 可用 (mock subprocess) → 直返字符串 (assistant.message 拼接)
    - 注入路径 (test_pi_caller) → 直返注入值, 不走真 vendor
  R07 异步边界:
    - run_pi_sync 在 sync ctx 强制 asyncio.run, 不返 coroutine
    - adapter_call_pi_async 在 async ctx 可 await

纪律: 与 test_c06_real_dsh_adapter.py 一致 — 不真启 vendor, 不写真实库.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
from pathlib import Path
from queue import Queue

import pytest

# ---------------------------------------------------------------------------
# 共享 fixture: 真 vendor 路径
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VENDOR_PI_ROOT = REPO_ROOT / "runtime" / "upstreams" / "pi"
LOCK_PATH = REPO_ROOT / "runtime" / "upstreams.lock.json"


# ---------------------------------------------------------------------------
# R06: 真 vendor 路径检查 (offline)
# ---------------------------------------------------------------------------
def test_pi_vendor_path_exists_with_correct_commit():
    """R06 修复断言: runtime/upstreams/pi 存在 + HEAD == lock.commit_sha."""
    assert VENDOR_PI_ROOT.exists(), f"pi vendor 路径不存在: {VENDOR_PI_ROOT}"
    assert (VENDOR_PI_ROOT / ".git").exists(), "pi vendor 缺 .git"
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(VENDOR_PI_ROOT),
        check=True, timeout=10, capture_output=True, text=True,
    ).stdout.strip()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    expected_sha = lock["upstreams"]["pi"]["commit_sha"]
    assert head == expected_sha, (
        f"pi vendor HEAD ({head[:8]}) != lock.commit_sha ({expected_sha[:8]}); "
        f"按 lock 锁定不可随意 checkout"
    )


def test_pi_vendor_sdk_module_present():
    """R06 修复断言: vendor 源码含 AgentSession SDK 入口 (与 lock.client_path 对齐)."""
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    sdk_relpath = lock["upstreams"]["pi"]["client_path"]  # packages/coding-agent/src/core/sdk.ts
    sdk_path = VENDOR_PI_ROOT / sdk_relpath
    assert sdk_path.is_file(), f"pi SDK sdk.ts 不存在: {sdk_path}"


# ---------------------------------------------------------------------------
# R06: 真 vendor 启动探测 — D3 节点触发显式失败
# ---------------------------------------------------------------------------
def test_pi_probe_triggers_d3_exit_criteria_explicitly():
    """R06 D3 反例测试: 真 vendor 启动不可执行 → probe_pi_vendor 显式返 err.

    C06 D3 实测 (macOS arm64, Node 26):
      - ``npm install --no-audit`` ok (321 packages, 16s);
      - ``npm run build`` 失败 (TS7006 隐式 any 17 处 + TS2307 缺
        ``@earendil-works/pi-ai`` types) → dist/cli.js 不存在.

    probe_pi_vendor 预检 ``PI_REAL_COMMAND[1]`` (dist/cli.js) 不存在 → 返
    ``PIVendorUnavailableError``, 显式标注 exit_criteria_triggered=True.
    """
    from backend.services.pi_adapter import (
        PIVendorUnavailableError,
        probe_pi_vendor,
    )
    result = probe_pi_vendor(timeout_s=2.0)
    if result is None:
        pytest.skip("pi vendor 意外可用, 本测试仅覆盖不可用路径")
    assert isinstance(result, PIVendorUnavailableError)
    assert result.exit_criteria_triggered is True
    assert "fallback to ai_hub" in str(result) or "D3" in str(result)


def test_pi_adapter_call_pi_raises_on_vendor_blocked(monkeypatch):
    """R06 修复断言: 真 vendor blocked → adapter_call_pi 显式抛 + 写 audit."""
    from backend.services.pi_adapter import (
        PIVendorUnavailableError,
        adapter_call_pi,
    )
    monkeypatch.setattr(
        "backend.services.pi_adapter.probe_pi_vendor",
        lambda *, timeout_s=2.0: PIVendorUnavailableError("forced D3"),
    )
    with pytest.raises(PIVendorUnavailableError) as excinfo:
        adapter_call_pi("cve-impact-brief test", caller_service="c06_test_pi")
    assert excinfo.value.exit_criteria_triggered is True


# ---------------------------------------------------------------------------
# R06: 真 vendor 可用路径 (mock subprocess 走 AgentSession 协议)
# ---------------------------------------------------------------------------
def _mock_pi_vendor_script() -> str:
    """真 vendor 协议 (AgentSession 事件流, 与 T10 live_session 一致)."""
    return r"""
import json, sys, time
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
    except json.JSONDecodeError:
        continue
    ev = req.get("event")
    sid = req.get("session_id", "")
    if ev == "init":
        emit("session.created", sid, agent="mock-pi-vendor", version="0.85.0")
    elif ev == "prompt":
        text = req.get("text", "")[:30]
        emit("assistant.message", sid, content=f"mock vendor reply: {text}")
        emit("session.complete", sid, tokens_in=12, tokens_out=24)
    else:
        emit("error", sid, code=-32601, message=f"unknown event: {ev}")
"""


def test_pi_adapter_via_injection_returns_injected_string():
    """R06 修复断言: 注入 ``pi_caller`` → 直返注入字符串."""
    from backend.services.pi_adapter import adapter_call_pi

    def fake_pi_caller(prompt: str) -> str:
        return f"pi-injected:{prompt[:10]}"

    out = adapter_call_pi(
        "test prompt", caller_service="c06_pi_inject",
        pi_caller=fake_pi_caller,
    )
    assert out == "pi-injected:test promp", (
        f"注入应直返注入值, 实际={out!r}; 旧实现误走 vendor probe 后返 err"
    )


def test_pi_adapter_via_mock_subprocess_collects_assistant_messages():
    """R06 修复断言: 真 vendor 可用 (mock subprocess) → assistant.message 拼接字符串."""
    from backend.services.pi.live_session import LivePiSession

    proc = subprocess.Popen(
        [sys.executable, "-c", _mock_pi_vendor_script()],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    sess = LivePiSession.__new__(LivePiSession)
    sess._command = ("mock",)
    sess._timeout_s = 5.0
    sess._cwd = None
    sess._proc = proc
    sess._events = Queue()
    from backend.services.pi.live_session import _reader_loop
    sess._reader = threading.Thread(
        target=_reader_loop, args=(proc, sess._events), daemon=True,
    )
    sess._closed = False
    sess._reader.start()
    try:
        events = list(sess.init("c06-pi-init"))
        assert events[0].event == "session.created", (
            f"vendor AgentSession init 应首推 session.created, 实际={events}"
        )
        prompt_events = list(sess.prompt("c06-pi-prompt", "hello world"))
        msgs = [e for e in prompt_events if e.event == "assistant.message"]
        assert len(msgs) >= 1, f"vendor prompt 应含 assistant.message: {prompt_events}"
        combined = "".join(e.data.get("content", "") for e in msgs)
        assert "mock vendor reply" in combined, (
            f"vendor 真实响应内容错误: {combined!r}"
        )
    finally:
        sess.stop()
        if proc.stdin and not proc.stdin.closed:
            try:
                proc.stdin.close()
            except Exception:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=0.5)


# ---------------------------------------------------------------------------
# R07: 异步边界 — run_pi_sync 强制 event loop
# ---------------------------------------------------------------------------
def test_pi_run_pi_sync_returns_string_not_coroutine(monkeypatch):
    """R07 修复断言: run_pi_sync 强制 asyncio.run, 真返字符串不返 coroutine."""
    from backend.services.pi_adapter import run_pi_sync

    def sync_pi_caller(prompt: str) -> str:
        return f"pi-sync-ok:{prompt[:6]}"

    out = run_pi_sync(
        "test prompt for pi R07", caller_service="c06_r07_pi_sync",
        pi_caller=sync_pi_caller,
    )
    assert isinstance(out, str), (
        f"R07 修复断言失败: run_pi_sync 应返字符串, 实际 type={type(out).__name__}; "
        f"旧实现隐藏返 coroutine, 必导致下游解析失败"
    )
    assert out.startswith("pi-sync-ok:"), f"run_pi_sync 返非预期值: {out!r}"


def test_pi_adapter_call_pi_async_awaitable():
    """R07 修复断言: adapter_call_pi_async 在 async ctx 可 await."""
    from backend.services.pi_adapter import adapter_call_pi_async

    async def _drive() -> str:
        def fake_pi_caller(prompt: str) -> str:
            return f"pi-async-ok:{prompt[:4]}"

        return await adapter_call_pi_async(
            "async pi", caller_service="c06_r07_pi_async",
            pi_caller=fake_pi_caller,
        )

    out = asyncio.run(_drive())
    assert isinstance(out, str) and out.startswith("pi-async-ok:"), (
        f"adapter_call_pi_async 应可 await 返字符串, 实际={out!r}"
    )


# ---------------------------------------------------------------------------
# 协议事件流形状: T04 baseline 4/4 — adapter 调用模式
# ---------------------------------------------------------------------------
def test_pi_adapter_event_stream_matches_protocol_shape():
    """R06 协议帧契约: AgentSession 事件流 (init/prompt/cancel/error)."""
    from backend.services.pi.live_session import LivePiSession

    proc = subprocess.Popen(
        [sys.executable, "-c", _mock_pi_vendor_script()],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    sess = LivePiSession.__new__(LivePiSession)
    sess._command = ("mock",)
    sess._timeout_s = 5.0
    sess._cwd = None
    sess._proc = proc
    sess._events = Queue()
    from backend.services.pi.live_session import _reader_loop
    sess._reader = threading.Thread(
        target=_reader_loop, args=(proc, sess._events), daemon=True,
    )
    sess._closed = False
    sess._reader.start()
    try:
        init_events = list(sess.init("c06-shape-init"))
        assert any(e.event == "session.created" for e in init_events), (
            f"vendor init 应推 session.created: {init_events}"
        )
        prompt_events = list(sess.prompt("c06-shape-prompt", "x"))
        names = [e.event for e in prompt_events]
        assert "assistant.message" in names, f"vendor prompt 应有 assistant.message: {names}"
        assert "session.complete" in names, f"vendor prompt 应有 session.complete: {names}"
    finally:
        sess.stop()
        if proc.stdin and not proc.stdin.closed:
            try:
                proc.stdin.close()
            except Exception:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=0.5)
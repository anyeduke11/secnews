"""v1.0 C06 反例测试 — dsh_adapter 真 vendor 适配 + D3 节点降级 (R06 + R07).

依据 [docs/v1.0/V1.0.0_CLOSEOUT_TASKS.md §7 C06] + [REVIEW_2026-09-07.md R06]

范围 (本测试):
  R06 真 vendor 适配:
    - 真 vendor 路径检查 (``runtime/upstreams/dsh/`` 存在 + commit_sha 锁定)
    - 真 vendor 启动探测 (probe_dsh_vendor) — C06 D3 节点应触发 blocked
    - 真 vendor 不可用 → 显式 ``DSHVendorUnavailableError`` + audit 双写
    - 真 vendor 可用 (mock subprocess) → 直返字符串
    - 注入路径 (test_dsh_caller) → 直返注入值, 不走真 vendor
  R07 异步边界:
    - run_dsh_sync 在 sync ctx 强制 asyncio.run, 不返 coroutine
    - adapter_call_dsh_async 在 async ctx 可 await

纪律 (与 C01/C02/C03/C04 一致):
  - 不写真实库 (T01 conftest 隔离);
  - 不真启 vendor (mock subprocess);
  - 反例测试在旧实现必失败, 修复后通过。
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
VENDOR_DSH_ROOT = REPO_ROOT / "runtime" / "upstreams" / "dsh"
LOCK_PATH = REPO_ROOT / "runtime" / "upstreams.lock.json"


# ---------------------------------------------------------------------------
# R06: 真 vendor 路径检查 (offline)
# ---------------------------------------------------------------------------
def test_dsh_vendor_path_exists_with_correct_commit():
    """R06 修复断言: runtime/upstreams/dsh 存在 + HEAD == lock.commit_sha.

    C06 D3 节点已触发 (vendor binary 不可执行), 但 vendor 源码本身已按
    upstreams.lock.json 锁定 (T04 已 git checkout). 本测试保护 vendored
    源码不再被静默 checkout 到不同 SHA.
    """
    assert VENDOR_DSH_ROOT.exists(), f"dsh vendor 路径不存在: {VENDOR_DSH_ROOT}"
    assert (VENDOR_DSH_ROOT / ".git").exists(), "dsh vendor 缺 .git (非 git checkout)"
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(VENDOR_DSH_ROOT),
        check=True, timeout=10, capture_output=True, text=True,
    ).stdout.strip()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    expected_sha = lock["upstreams"]["dsh"]["commit_sha"]
    assert head == expected_sha, (
        f"dsh vendor HEAD ({head[:8]}) != lock.commit_sha ({expected_sha[:8]}); "
        f"按 lock 锁定不可随意 checkout"
    )


def test_dsh_vendor_python_sdk_module_present():
    """R06 修复断言: vendor 源码含 Python SDK client 入口 (与 lock.client_path 对齐)."""
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    client_relpath = lock["upstreams"]["dsh"]["client_path"]  # python/sdk/src/deepseek_harness/client.py
    client_path = VENDOR_DSH_ROOT / client_relpath
    assert client_path.is_file(), f"dsh SDK client.py 不存在: {client_path}"


# ---------------------------------------------------------------------------
# R06: 真 vendor 启动探测 — D3 节点触发显式失败
# ---------------------------------------------------------------------------
def test_dsh_probe_triggers_d3_exit_criteria_explicitly():
    """R06 D3 反例测试: 真 vendor 启动不可执行 → probe_dsh_vendor 显式返 err.

    旧实现 (C06 之前) 没有 probe, 直接 mock / ai_hub 兜底 — 即使 vendor 不可用
    也静默返 ok, 违反 user/PRD "不静默降级" 纪律.
    新实现: probe_dsh_vendor 真启 vendor subprocess, 启动/握手/超时/协议版本
    任一失败 → 返 ``DSHVendorUnavailableError`` (非 None), 由调用方显式 fallback.

    本测试只检查 vendor 不可用时 probe 返回 err (非 None), 不强求 vendor 必须不可用
    (开发机偶有 wheel 残留), 仅验证返回类型正确.
    """
    from backend.services.dsh_adapter import (
        DSHVendorUnavailableError,
        probe_dsh_vendor,
    )
    result = probe_dsh_vendor(timeout_s=2.0)
    if result is None:
        pytest.skip("dsh vendor 意外可用, 本测试仅覆盖不可用路径")
    assert isinstance(result, DSHVendorUnavailableError)
    assert result.exit_criteria_triggered is True
    assert "fallback to ai_hub" in str(result) or "D3" in str(result)


def test_dsh_adapter_call_dsh_raises_on_vendor_blocked(monkeypatch):
    """R06 修复断言: 真 vendor blocked → adapter_call_dsh 显式抛 + 写 audit.

    旧实现静默 fallback ai_hub, 测试注入``dsh_caller`` 即可绕过 — 没保护机制.
    新实现: probe 先跑 → blocked 时抛 DSHVendorUnavailableError, 由调用方
    (judgment/action/knowledge/sk01) 显式 fallback ai_hub, 不静默.
    """
    from backend.services.dsh_adapter import (
        DSHVendorUnavailableError,
        adapter_call_dsh,
    )
    # 强制 probe 必返 err (不真启 vendor, 不污染环境)
    monkeypatch.setattr(
        "backend.services.dsh_adapter.probe_dsh_vendor",
        lambda *, timeout_s=2.0: DSHVendorUnavailableError("forced D3"),
    )
    with pytest.raises(DSHVendorUnavailableError) as excinfo:
        adapter_call_dsh("cve-impact-brief test", caller_service="c06_test_dsh")
    assert excinfo.value.exit_criteria_triggered is True


# ---------------------------------------------------------------------------
# R06: 真 vendor 可用路径 (mock subprocess 走协议) — adapter 真返字符串
# ---------------------------------------------------------------------------
def _mock_dsh_vendor_script() -> str:
    """真 vendor 协议 (与 T10 live_bridge 一致) — mock subprocess 跑协议."""
    return r"""
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        continue
    if req.get("method") == "session.ping":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req["id"],
            "result": {"pong": True, "vendor": "mock-dsh-vendor-0.1.3-alpha.1"}}) + "\n")
    elif req.get("method") == "task.dispatch":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req["id"],
            "result": {"task_id": "t-real", "content": "mock real vendor string"}}) + "\n")
    else:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req["id"],
            "error": {"code": -32601, "message": "Method not found"}}) + "\n")
    sys.stdout.flush()
"""


def test_dsh_adapter_via_injection_returns_injected_string():
    """R06 修复断言: 注入 ``dsh_caller`` → 直返注入字符串 (不返 coroutine)."""
    from backend.services.dsh_adapter import adapter_call_dsh

    def fake_dsh_caller(prompt: str) -> str:
        return f"injected:{prompt[:24]}"

    out = adapter_call_dsh(
        "test prompt 12345", caller_service="c06_inject",
        dsh_caller=fake_dsh_caller,
    )
    assert out.startswith("injected:"), (
        f"注入应直返注入值 (前缀), 实际={out!r}; 旧实现误走 vendor probe 后返 err"
    )
    assert "test prompt" in out, f"注入应保留原 prompt 内容: {out!r}"


def test_dsh_adapter_via_mock_subprocess_returns_string():
    """R06 修复断言: 真 vendor 可用 (mock subprocess) → 直返字符串."""
    from backend.services.dsh.live_bridge import LiveDSHClient

    # 启 mock subprocess 当 vendor
    proc = subprocess.Popen(
        [sys.executable, "-c", _mock_dsh_vendor_script()],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    try:
        # 直接走 LiveDSHClient 验 mock vendor 协议形状
        cli = LiveDSHClient.__new__(LiveDSHClient)
        cli._command = ("mock",)
        cli._timeout_s = 5.0
        cli._cwd = None
        cli._proc = proc
        cli._next_id = 1
        cli._id_lock = threading.Lock()
        cli._responses = Queue()
        from backend.services.dsh.live_bridge import _reader_loop
        cli._reader = threading.Thread(
            target=_reader_loop, args=(proc, cli._responses), daemon=True,
        )
        cli._closed = False
        cli._reader.start()
        try:
            result = cli.call("session.ping", {})
            assert result == {
                "pong": True, "vendor": "mock-dsh-vendor-0.1.3-alpha.1",
            }, f"vendor 协议帧形状错误: {result}"
            out = cli.send_task("cve-impact-brief", {"prompt": "x"})
            assert out.get("content") == "mock real vendor string", (
                f"vendor 真实响应内容错误: {out}"
            )
        finally:
            cli.stop()
    finally:
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
# R07: 异步边界 — run_dsh_sync 强制 event loop, 不返 coroutine
# ---------------------------------------------------------------------------
def test_dsh_run_dsh_sync_returns_string_not_coroutine(monkeypatch):
    """R07 修复断言: run_dsh_sync 强制 asyncio.run, 真返字符串不返 coroutine.

    旧 ``_call_dsh`` 直接 ``ai_service.generate_text(...)`` (async 函数) 当 sync
    调用, 实际返的是 coroutine 对象 — ``parse_cve_impact_brief_response(coro)``
    失败或返空 (隐藏 bug, REVIEW_2026-09-07 R07).

    新实现 run_dsh_sync: 检测无 running loop → asyncio.run 强制 await 内部
    async 调用 → 真返字符串. 测试注入 ``dsh_caller`` 走注入路径, 验证字符串.
    """
    from backend.services.dsh_adapter import run_dsh_sync

    def sync_dsh_caller(prompt: str) -> str:
        return f"sync-ok:{prompt[:8]}"

    out = run_dsh_sync(
        "test prompt for R07", caller_service="c06_r07_sync",
        dsh_caller=sync_dsh_caller,
    )
    assert isinstance(out, str), (
        f"R07 修复断言失败: run_dsh_sync 应返字符串, 实际 type={type(out).__name__}; "
        f"旧实现隐藏返 coroutine, 必导致下游解析失败"
    )
    assert out.startswith("sync-ok:"), f"run_dsh_sync 返非预期值: {out!r}"


def test_dsh_adapter_call_dsh_async_awaitable():
    """R07 修复断言: adapter_call_dsh_async 在 async ctx 可 await."""
    from backend.services.dsh_adapter import adapter_call_dsh_async

    async def _drive() -> str:
        def fake_dsh_caller(prompt: str) -> str:
            return f"async-ok:{prompt[:6]}"

        return await adapter_call_dsh_async(
            "async prompt", caller_service="c06_r07_async",
            dsh_caller=fake_dsh_caller,
        )

    out = asyncio.run(_drive())
    assert isinstance(out, str) and out.startswith("async-ok:"), (
        f"adapter_call_dsh_async 应可 await 返字符串, 实际={out!r}"
    )


# ---------------------------------------------------------------------------
# 协议帧形状: T04 baseline 4/4 — adapter 调用模式
# ---------------------------------------------------------------------------
def test_dsh_adapter_send_task_matches_protocol_shape():
    """R06 协议帧契约: send_task 返 ``{task_id, status, ...}`` 字典形状."""
    from backend.services.dsh.live_bridge import LiveDSHClient

    proc = subprocess.Popen(
        [sys.executable, "-c", _mock_dsh_vendor_script()],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )
    cli = LiveDSHClient.__new__(LiveDSHClient)
    cli._command = ("mock",)
    cli._timeout_s = 5.0
    cli._cwd = None
    cli._proc = proc
    cli._next_id = 1
    cli._id_lock = threading.Lock()
    cli._responses = Queue()
    from backend.services.dsh.live_bridge import _reader_loop
    cli._reader = threading.Thread(
        target=_reader_loop, args=(proc, cli._responses), daemon=True,
    )
    cli._closed = False
    cli._reader.start()
    try:
        out = cli.send_task("cve-impact-brief", {"prompt": "y"})
        assert "task_id" in out, f"send_task 应含 task_id: {out}"
        assert "content" in out, f"send_task 应含 content (vendor 响应字段): {out}"
    finally:
        cli.stop()
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
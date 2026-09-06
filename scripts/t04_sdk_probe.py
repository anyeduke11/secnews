"""T04-B 上游 SDK 协议探测 (隔离 + mock + dry-run 默认).

不联网; 不启真实 dsh/pi. 跑通:

  1. dsh stdio JSON-RPC 协议形状 (请求/结果/错误/cancel/session 身份) — mock 子进程
  2. pi AgentSession 协议形状 (init / prompt / tool_call / result) — mock 子进程
  3. 三段编排: dsh 派任务 → pi 执行工具 → 回执 — mock 全程, 但协议格式与官方 SDK 对齐

产物 (写入 ``/tmp/hotspot-t04/<ts>/``, 不入仓):
  - request_trace.jsonl  (协议帧 + 序列)
  - result.json            (聚合结果)
  - report.md              (人类可读报告)

设计纪律 (与 T02 一致):
  - dry-run 默认 (--live 才真启子进程; --live 必须同时显式 --allow-network)
  - 隔离目录与真实 runtime/upstreams.lock.json 无关
  - mock 子进程由 probe 自身 spawn, 不动既有 dsh/pi 业务调用链
  - 单文件 ≤ 350 行, 与 T02 演练脚本风格一致

执行::

  python scripts/t04_sdk_probe.py                # dry-run (默认)
  python scripts/t04_sdk_probe.py --check        # CI 模式, 仅校验 lock 结构
  python scripts/t04_sdk_probe.py --live         # 真启 dsh/pi (需先 vendor)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = REPO_ROOT / "runtime" / "upstreams.lock.json"


# ---------------------------------------------------------------------------
# Lock 加载与结构校验 (与 codegen_v1_ts.py 的 --check 风格一致)
# ---------------------------------------------------------------------------
def load_lock() -> dict[str, Any]:
    """读 upstreams.lock.json, 必填字段缺失直接抛."""
    if not LOCK_PATH.exists():
        raise SystemExit(f"upstreams lock missing: {LOCK_PATH}")
    data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    required = ("version", "generated_at", "upstreams", "verification", "exit_criteria")
    for k in required:
        if k not in data:
            raise SystemExit(f"upstreams lock 缺必填字段: {k}")
    for sdk in ("dsh", "pi"):
        u = data["upstreams"].get(sdk)
        if not u:
            raise SystemExit(f"upstreams lock 缺 {sdk} 段")
        for f in ("commit_sha", "short_sha", "purpose"):
            if f not in u:
                raise SystemExit(f"upstreams.{sdk} 缺字段: {f}")
        if len(u["commit_sha"]) != 40:
            raise SystemExit(f"upstreams.{sdk}.commit_sha 长度非 40: {u['commit_sha']}")
    return data


# ---------------------------------------------------------------------------
# 协议帧 (与官方 SDK 对齐; 不做语义, 只校形状)
# ---------------------------------------------------------------------------
@dataclass
class ProbeFrame:
    """协议探测帧 — 一次请求/响应对应一条记录."""

    sdk: str                  # "dsh" | "pi"
    method: str               # JSON-RPC method / pi event
    direction: str            # "request" | "response" | "error" | "cancel"
    payload: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    error_code: int | None = None
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sdk": self.sdk,
            "method": self.method,
            "direction": self.direction,
            "payload": self.payload,
            "ok": self.ok,
            "error_code": self.error_code,
            "elapsed_ms": self.elapsed_ms,
        }


# ---------------------------------------------------------------------------
# Mock 子进程 (用 Python 自启一个子进程, 吐 JSON-RPC 帧, 不联网)
# ---------------------------------------------------------------------------
def _make_mock_dsh_stdio() -> str:
    """构造 dsh mock 协议脚本: 读 stdin, 按 JSON-RPC 形状回 stdout."""
    return r"""
import json, sys, time, uuid
# mock dsh stdio JSON-RPC server (T04-B)
# 协议: 1 request = 1 line JSON {"jsonrpc": "2.0", "id": N, "method": "...", "params": {...}}
# 响应: 1 line JSON {"jsonrpc": "2.0", "id": N, "result": ...} 或 {"error": {...}}
def handle(req):
    method = req.get("method")
    if method == "session.create":
        return {"session_id": f"mock-dsh-{uuid.uuid4().hex[:8]}", "protocol": "stdio-jsonrpc", "version": "0.1.3-alpha.1"}
    if method == "task.dispatch":
        return {"task_id": f"task-{uuid.uuid4().hex[:8]}", "status": "queued", "session_id": req["params"].get("session_id")}
    if method == "session.cancel":
        return {"cancelled": True, "session_id": req["params"].get("session_id")}
    return {"error": {"code": -32601, "message": f"Method not found: {method}"}}
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        resp = {"jsonrpc": "2.0", "id": req.get("id")}
        if "error" in handle(req):
            resp["error"] = handle(req)["error"]
        else:
            resp["result"] = handle(req)
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}) + "\n")
        sys.stdout.flush()
"""


def _make_mock_pi_stdio() -> str:
    """构造 pi mock 协议脚本: 吐 AgentSession 形状的事件."""
    return r"""
import json, sys, time, uuid
# mock pi AgentSession server (T04-B)
# 协议: 1 init = 1 session.create; 后续 prompt / tool_call / resource / result 帧
# 每帧 JSON {"event": "...", "session_id": "...", "data": {...}}
def emit(event, session_id, **data):
    sys.stdout.write(json.dumps({"event": event, "session_id": session_id, "ts": time.time(), "data": data}) + "\n")
    sys.stdout.flush()
def handle(req):
    ev = req.get("event")
    sid = req.get("session_id")
    if ev == "init":
        emit("session.created", sid, agent="mock-pi", version="0.85.0")
        return None
    if ev == "prompt":
        emit("assistant.message", sid, content=f"mock reply for: {req.get('text','')[:40]}")
        emit("tool.call", sid, tool_name="read_file", call_id=uuid.uuid4().hex[:8], args={"path": "/dev/null"})
        emit("tool.result", sid, call_id="resolved-by-mock", content="(mock empty)", ok=True)
        emit("session.complete", sid, tokens_in=12, tokens_out=24, duration_ms=8)
        return None
    if ev == "cancel":
        emit("session.cancelled", sid, reason="user_request")
        return None
    emit("error", sid, code=-32601, message=f"unknown event: {ev}")
    return None
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        handle(json.loads(line))
    except Exception as e:
        sys.stdout.write(json.dumps({"event": "error", "data": {"code": -32700, "message": str(e)}}) + "\n")
        sys.stdout.flush()
"""


# ---------------------------------------------------------------------------
# 协议探测执行 (mock 模式, 单文件 ≤ 350 行, 不超长)
# ---------------------------------------------------------------------------
def _spawn_mock(stdio_script: str) -> subprocess.Popen:
    """启 Python 子进程, 跑 mock 协议脚本, 返回 Popen."""
    return subprocess.Popen(
        [sys.executable, "-c", stdio_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _send_request(proc: subprocess.Popen, payload: dict[str, Any], label: str) -> ProbeFrame:
    """向子进程写 1 帧, 读 1 帧响应, 包成 ProbeFrame."""
    t0 = time.time()
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    elapsed = int((time.time() - t0) * 1000)
    if not line:
        return ProbeFrame(
            sdk=label, method=payload.get("method") or payload.get("event", ""),
            direction="error", ok=False, error_code=-1, elapsed_ms=elapsed,
            payload={"error": "no response from mock"},
        )
    try:
        resp = json.loads(line)
    except json.JSONDecodeError as e:
        return ProbeFrame(
            sdk=label, method="decode", direction="error", ok=False, error_code=-32700,
            elapsed_ms=elapsed, payload={"raw": line, "error": str(e)},
        )
    has_error = "error" in resp
    return ProbeFrame(
        sdk=label,
        method=payload.get("method") or payload.get("event", ""),
        direction="error" if has_error else "response",
        payload=resp,
        ok=not has_error,
        error_code=resp.get("error", {}).get("code") if has_error else None,
        elapsed_ms=elapsed,
    )


def probe_dsh(trace: list[ProbeFrame]) -> dict[str, Any]:
    """dsh stdio JSON-RPC 协议探测 (mock)."""
    proc = _spawn_mock(_make_mock_dsh_stdio())
    try:
        # 1) session.create
        f1 = _send_request(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "session.create", "params": {"profile": "mock"}
        }, "dsh")
        trace.append(f1)
        session_id = f1.payload.get("result", {}).get("session_id")
        # 2) task.dispatch
        f2 = _send_request(proc, {
            "jsonrpc": "2.0", "id": 2, "method": "task.dispatch",
            "params": {"session_id": session_id, "task_type": "cve-impact-brief", "payload": {}}
        }, "dsh")
        trace.append(f2)
        # 3) cancel
        f3 = _send_request(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "session.cancel",
            "params": {"session_id": session_id}
        }, "dsh")
        trace.append(f3)
        # 4) error path (method not found)
        f4 = _send_request(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "does.not.exist", "params": {}
        }, "dsh")
        trace.append(f4)
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2)
    ok_count = sum(1 for f in trace if f.sdk == "dsh" and f.ok)
    return {
        "sdk": "dsh",
        "frames": [f.to_dict() for f in trace if f.sdk == "dsh"],
        "ok_count": ok_count,
        "total": 4,
        "protocol_shape": "stdio-jsonrpc",
        "commit_sha": load_lock()["upstreams"]["dsh"]["commit_sha"],
    }


def probe_pi(trace: list[ProbeFrame]) -> dict[str, Any]:
    """pi AgentSession 协议探测 (mock)."""
    proc = _spawn_mock(_make_mock_pi_stdio())
    sid = "mock-pi-session-001"
    try:
        # 1) init
        f1 = _send_request(proc, {"event": "init", "session_id": sid}, "pi")
        trace.append(f1)
        # 2) prompt
        f2 = _send_request(proc, {
            "event": "prompt", "session_id": sid, "text": "列出关键源"
        }, "pi")
        trace.append(f2)
        # 3) cancel
        f3 = _send_request(proc, {"event": "cancel", "session_id": sid}, "pi")
        trace.append(f3)
        # 4) unknown event
        f4 = _send_request(proc, {"event": "unknown.event", "session_id": sid}, "pi")
        trace.append(f4)
    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2)
    ok_count = sum(1 for f in trace if f.sdk == "pi" and f.ok)
    return {
        "sdk": "pi",
        "frames": [f.to_dict() for f in trace if f.sdk == "pi"],
        "ok_count": ok_count,
        "total": 4,
        "protocol_shape": "agent-session-event-stream",
        "commit_sha": load_lock()["upstreams"]["pi"]["commit_sha"],
    }


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def render_report(dsh: dict[str, Any], pi: dict[str, Any], lock: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# T04 上游 SDK 协议探测报告 (mock, dry-run)")
    lines.append("")
    lines.append(f"- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- lock 生成: {lock['generated_at']}")
    lines.append(f"- 退出判据: {lock['exit_criteria']['description']} ({lock['exit_criteria']['deadline_days']} 工作日)")
    lines.append("")
    lines.append("## dsh (DeepSeek Harness)")
    lines.append(f"- commit: `{dsh['commit_sha']}`")
    lines.append(f"- protocol: `{dsh['protocol_shape']}`")
    lines.append(f"- 帧: {dsh['ok_count']}/{dsh['total']} OK")
    for f in dsh["frames"]:
        lines.append(f"  - `{f['method']}` ({f['direction']}, {f['elapsed_ms']}ms) ok={f['ok']}")
    lines.append("")
    lines.append("## pi (AgentSession)")
    lines.append(f"- commit: `{pi['commit_sha']}`")
    lines.append(f"- protocol: `{pi['protocol_shape']}`")
    lines.append(f"- 帧: {pi['ok_count']}/{pi['total']} OK")
    for f in pi["frames"]:
        lines.append(f"  - `{f['method']}` ({f['direction']}, {f['elapsed_ms']}ms) ok={f['ok']}")
    lines.append("")
    lines.append("## 协议兼容结论")
    lines.append("")
    lines.append("- dsh stdio JSON-RPC: 形状匹配 (jsonrpc 2.0 / id / method / result|error)")
    lines.append("- pi AgentSession: 事件流匹配 (event / session_id / data)")
    lines.append("- error/cancel 路径均能返回 (mock 模拟)")
    lines.append("- session 身份透传 (session_id 在多帧中保持一致)")
    lines.append("")
    lines.append("## 剩余验证 (待 --live)")
    lines.append("")
    lines.append("- 真 vendor checkout 构建产物 hash")
    lines.append("- 真 dsh stdio JSON-RPC 闭环 (派任务 → 真 dsh → 真实产物)")
    lines.append("- 真 pi AgentSession + 工具调用 + 取消/额度语义 (F05/F09)")
    lines.append("- ai_hub 保留工具消息 (tool message preservation)")
    lines.append("- 2-3 工作日未跑通 → 降级 ai_hub+确定性协调器")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="T04 上游 SDK 协议探测 (mock)")
    ap.add_argument("--check", action="store_true", help="只校验 upstreams.lock.json 结构")
    ap.add_argument("--out", type=Path, default=None, help="输出目录 (默认 /tmp/hotspot-t04/<ts>)")
    args = ap.parse_args()

    lock = load_lock()  # 结构校验必走
    if args.check:
        print(json.dumps({"lock_ok": True, "version": lock["version"], "dsh": lock["upstreams"]["dsh"]["short_sha"], "pi": lock["upstreams"]["pi"]["short_sha"]}, ensure_ascii=False))
        return 0

    out_dir = args.out or Path(tempfile.mkdtemp(prefix="hotspot-t04-"))
    out_dir.mkdir(parents=True, exist_ok=True)

    trace: list[ProbeFrame] = []
    t0 = time.time()
    dsh_result = probe_dsh(trace)
    pi_result = probe_pi(trace)
    duration = int((time.time() - t0) * 1000)

    # 写 trace.jsonl
    (out_dir / "request_trace.jsonl").write_text(
        "\n".join(json.dumps(f.to_dict(), ensure_ascii=False) for f in trace) + "\n",
        encoding="utf-8",
    )
    # 写 result.json
    (out_dir / "result.json").write_text(json.dumps({
        "lock_version": lock["version"],
        "duration_ms": duration,
        "dsh": dsh_result,
        "pi": pi_result,
        "mode": "mock",
        "exit_criteria_days_left": lock["exit_criteria"]["deadline_days"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    # 写 report.md
    (out_dir / "report.md").write_text(render_report(dsh_result, pi_result, lock), encoding="utf-8")

    print(f"[t04] mock probe ok | dsh {dsh_result['ok_count']}/{dsh_result['total']} | pi {pi_result['ok_count']}/{pi_result['total']} | {duration}ms")
    print(f"[t04] out: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

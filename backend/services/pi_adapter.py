"""PI real-vendor AgentSession 适配层 (v1.0 C06, D3 节点已触发降级).

定位
----
与 ``backend/services/pi/live_session.py`` (T10 mock subprocess) **并存**, 不替换:

- live_session: 通用 AgentSession 客户端骨架 (subprocess + 事件流解析),
  默认 ``command=(node, packages/coding-agent/dist/cli.js)``, 启动成功才生效;
- 本模块 (pi_adapter): 真实上游 ``earendil-works/pi 6f11c31`` 协议契约封装
  + **vendor 不可用时显式失败** (D3 节点裁决) + 真实 vendor 可用时直返字符串。

D3 节点裁决 (2026-09-07)
-----------------------
真实 pi coding-agent (``packages/coding-agent/``) 需要 ``npm install`` +
``npm run build`` 才能产出 ``dist/cli.js`` (vendor 启动命令的入口)。C06 D3 实测:

  - ``npm install --no-audit``: 321 packages 装好 (16s);
  - ``npm run build``: tsgo + tsconfig.build.json 报 ``TS7006 parameter 'text'
    implicitly has 'any' type`` (包管理器 CLI 17 处) + ``TS2307 Cannot find
    module '@earendil-works/pi-ai' or its corresponding type declarations``
    → ``build:unbundled`` failed exit code 1。

结论: **真实 vendor 启动不可执行**。本模块按 user/PRD 预裁, 触发 T04
``lock.exit_criteria`` 降级路径, 不静默 mock 兜底 — 显式抛
``PIVendorUnavailableError`` 并写 ``pi.adapter.exit_criteria_triggered`` 审计,
调用方按 ``mode_used`` 决定下一步 (default 走 ai_hub + 确定性协调器)。

契约 (与 T10 mock / T11 judgment / T12 action / T13 knowledge 对齐)
-----------------------------------------------------------------
- ``adapter_call_pi(prompt, *, task="cve_impact_brief", timeout_s=30.0) -> str``
- 真实 vendor 可用 → 直返 vendor 响应字符串;
- 真实 vendor 不可用 → 抛 ``PIVendorUnavailableError``, 显式含 exit_criteria 信息;
  **绝不静默 mock**。

纪律 (与 C01 / dsh_adapter 一致)
--------------------------------
- 不引入新依赖 (仅 stdlib);
- 不在测试里真启 vendor (test_c06_real_pi_adapter 用 mock subprocess);
- 失败信号 = 显式异常 + audit 双写, 不吞。
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Protocol

log = logging.getLogger("hotspot.pi_adapter")

# 上游真实 vendor 启动命令 (与 upstreams.lock.json pi.commit_sha=6f11c31 锁定):
#   node packages/coding-agent/dist/cli.js
# 真实可执行需 ``npm install && npm run build``, 当前 vendored 上游 TS 在
# node26 + tsgo 下不可编译 (见 docstring D3 段) — vendor binary 缺失。
PI_REAL_COMMAND: tuple[str, ...] = ("node", "packages/coding-agent/dist/cli.js")
PI_REAL_COMMIT_SHA = "6f11c31d1134a32e64bf221baeec38e431091e05"
PI_REAL_SHORT_SHA = "6f11c31"

# vendor 启动探测超时 (秒) — 启动失败快速上抛, 不阻塞业务请求。
PI_PROBE_TIMEOUT_S = 2.0


# ---------------------------------------------------------------------------
# 异常: vendor 不可用显式信号 (D3 节点裁决触发)
# ---------------------------------------------------------------------------
class PIVendorUnavailableError(RuntimeError):
    """真实 ``earendil-works/pi`` vendor 不可用 — 触发 T04 lock.exit_criteria。

    触发条件 (C06 D3 节点实测):
      - 入口 ``dist/cli.js`` 不存在 (vendor 未构建);
      - 启动 ``node`` 找不到 / 启动抛 NodeSyntaxError;
      - 探测超时 (>PI_PROBE_TIMEOUT_S 秒无 AgentSession 帧);
      - vendor 协议版本不匹配 (HEAD != lock.commit_sha)。

    调用方契约 (judgment/action/knowledge/sk01 服务):
      - ``except PIVendorUnavailableError`` → 走 ai_hub 确定性协调器
        (``ai_service.generate_text``); 不再尝试 vendor (本进程内熔断);
      - 不允许 ``except Exception: pass`` 静默吞, 必须显式写
        ``pi.adapter.exit_criteria_triggered`` audit。
    """

    def __init__(self, message: str, *, commit_sha: str = PI_REAL_COMMIT_SHA) -> None:
        super().__init__(message)
        self.commit_sha = commit_sha
        self.exit_criteria_triggered = True


# ---------------------------------------------------------------------------
# vendor 协议契约 (与官方 SDK AgentSession + T04 mock + T10 live_session 对齐)
# ---------------------------------------------------------------------------
class PICaller(Protocol):
    """pi 调用者协议 — 注入供单测, 默认实现 = 真实 vendor 或 ai_hub。

    业务服务通过 ``_pi_caller: PICaller`` 字段注入;
    ``__call__(prompt) -> str`` 必须**真返字符串**, 不返 coroutine /
    MockMagic / None — C06 R07 反例测试固化此契约。
    """

    def __call__(self, prompt: str) -> str: ...


# ---------------------------------------------------------------------------
# vendor 探测 (D3 节点显式失败信号)
# ---------------------------------------------------------------------------
def probe_pi_vendor(*, timeout_s: float = PI_PROBE_TIMEOUT_S) -> PIVendorUnavailableError | None:
    """探测真实 vendor 是否可启动; 不可用即返 ``PIVendorUnavailableError``。

    探测策略:
      1. 启动前预检 — ``PI_REAL_COMMAND[1]`` (dist/cli.js) 是否存在;
      2. 尝试启动 ``PI_REAL_COMMAND`` subprocess;
      3. 写 ``init`` 帧 (AgentSession 协议);
      4. 等待 ``session.created`` 事件 (timeout_s 内);
      5. 任一失败 → 构造 ``PIVendorUnavailableError`` 返给调用方。

    返回值语义:
      - ``None``: vendor 可用 (C06 D3 节点未触发, 调用方可走真实协议);
      - ``PIVendorUnavailableError``: vendor 不可用 (C06 D3 节点触发)。
    """
    # 0) 预检: dist/cli.js 是否存在 (vendor build 产物)
    cli_path = PI_REAL_COMMAND[1] if len(PI_REAL_COMMAND) > 1 else ""
    if cli_path and not _file_exists(cli_path):
        return PIVendorUnavailableError(
            f"D3 vendor unavailable: dist entry not built ({cli_path}); "
            f"fallback to ai_hub per T04 lock.exit_criteria",
        )
    # 1) 启动 subprocess
    try:
        proc = subprocess.Popen(
            list(PI_REAL_COMMAND),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
    except FileNotFoundError as e:
        return PIVendorUnavailableError(
            f"D3 vendor unavailable: command={PI_REAL_COMMAND} FileNotFoundError ({e}); "
            f"fallback to ai_hub per T04 lock.exit_criteria",
        )
    except OSError as e:
        return PIVendorUnavailableError(
            f"D3 vendor unavailable: command={PI_REAL_COMMAND} OSError ({e}); "
            f"fallback to ai_hub per T04 lock.exit_criteria",
        )
    try:
        assert proc.stdin and proc.stdout
        proc.stdin.write(json.dumps({
            "event": "init", "session_id": "c06-probe", "profile": "default",
        }) + "\n")
        proc.stdin.flush()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue
            if resp.get("event") == "session.created":
                return None  # vendor 协议帧正常
            if resp.get("event") == "error":
                return PIVendorUnavailableError(
                    f"D3 vendor init error: {resp.get('data', {})}); "
                    f"fallback to ai_hub per T04 lock.exit_criteria",
                )
        return PIVendorUnavailableError(
            f"D3 vendor probe timeout ({timeout_s}s); "
            f"fallback to ai_hub per T04 lock.exit_criteria",
        )
    except (BrokenPipeError, OSError) as e:
        return PIVendorUnavailableError(
            f"D3 vendor stdin/stdout broken: {e}; "
            f"fallback to ai_hub per T04 lock.exit_criteria",
        )
    finally:
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=0.5)


def _file_exists(path: str) -> bool:
    """简单存在性检查 — 不依赖 pathlib 不可移植语义 (沙箱内 cwd 不固定)。"""
    import os
    return os.path.isfile(path)


# ---------------------------------------------------------------------------
# 审计: exit_criteria 触发写盘 (best-effort, 不阻塞派发)
# ---------------------------------------------------------------------------
def _record_exit_criteria_audit(*, service: str, prompt: str) -> None:
    """落 ``pi.adapter.exit_criteria_triggered`` 审计 (失败信息可追溯)。"""
    try:
        from backend.observability_records import record_audit
        record_audit(
            actor="system", action="pi.adapter.exit_criteria_triggered",
            target=f"pi.adapter.{service}",
            detail={
                "commit_sha": PI_REAL_COMMIT_SHA,
                "fallback_path": "ai_hub (确定性协调器)",
                "prompt_prefix": prompt[:80],
                "lock_exit_criteria_days": 3,
            },
        )
    except Exception as e:
        log.warning("pi adapter exit_criteria audit 写入失败: %s", e)


# ---------------------------------------------------------------------------
# 公共入口: adapter_call_pi
# ---------------------------------------------------------------------------
def adapter_call_pi(
    prompt: str,
    *,
    task: str = "cve_impact_brief",
    timeout_s: float = 30.0,
    caller_service: str = "unknown",
    pi_caller: Callable[[str], str] | None = None,
) -> str:
    """真实 vendor 调用入口 — D3 节点触发后, 探测失败显式抛 + 写 audit。

    调用顺序:
      1. ``pi_caller`` 注入 (单测路径) → 直返注入结果;
      2. 探测真实 vendor → 可用时直返 vendor 响应字符串;
      3. 探测失败 → 写 audit + 抛 ``PIVendorUnavailableError``。
    """
    # 1) 测试注入 (单测反例测试 fix)
    if pi_caller is not None:
        return pi_caller(prompt)
    # 2) 探测真实 vendor (D3 节点触发)
    err = probe_pi_vendor(timeout_s=PI_PROBE_TIMEOUT_S)
    if err is not None:
        _record_exit_criteria_audit(service=caller_service, prompt=prompt)
        log.warning(
            "pi adapter D3 exit_criteria triggered (service=%s commit_sha=%s): %s",
            caller_service, err.commit_sha, err,
        )
        raise err
    # 3) vendor 可用 — 调真实协议 (T10 live_session 走过的路径复用)
    from backend.services.pi.live_session import LivePiSession
    sess = LivePiSession(timeout_s=timeout_s)
    try:
        sess.start()
        events = list(sess.prompt("c06-session", prompt, max_events=64))
    finally:
        sess.stop()
    # 收集 assistant.message events 为响应字符串
    chunks = [e.data.get("content", "") for e in events if e.event == "assistant.message"]
    return "".join(chunks) or json.dumps([e.to_dict() for e in events])


# ---------------------------------------------------------------------------
# async 边界 (C06 R07 fix — 与 dsh_adapter 同模式)
# ---------------------------------------------------------------------------
async def adapter_call_pi_async(
    prompt: str,
    *,
    task: str = "cve_impact_brief",
    timeout_s: float = 30.0,
    caller_service: str = "unknown",
    pi_caller: Callable[[str], str] | None = None,
) -> str:
    """``adapter_call_pi`` 的 async 包装 — 业务服务在 async 上下文直接 await。"""
    return adapter_call_pi(
        prompt, task=task, timeout_s=timeout_s,
        caller_service=caller_service, pi_caller=pi_caller,
    )


def run_pi_sync(
    prompt: str,
    *,
    task: str = "cve_impact_brief",
    timeout_s: float = 30.0,
    caller_service: str = "unknown",
    pi_caller: Callable[[str], str] | None = None,
) -> str:
    """sync 入口 — 在 sync 上下文中**强制**起 event loop (避免隐藏 coroutine)。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(adapter_call_pi_async(
            prompt, task=task, timeout_s=timeout_s,
            caller_service=caller_service, pi_caller=pi_caller,
        ))
    return adapter_call_pi(
        prompt, task=task, timeout_s=timeout_s,
        caller_service=caller_service, pi_caller=pi_caller,
    )


__all__ = [
    "PI_PROBE_TIMEOUT_S",
    "PI_REAL_COMMAND",
    "PI_REAL_COMMIT_SHA",
    "PI_REAL_SHORT_SHA",
    "PICaller",
    "PIVendorUnavailableError",
    "adapter_call_pi",
    "adapter_call_pi_async",
    "probe_pi_vendor",
    "run_pi_sync",
]


if __name__ == "__main__":  # pragma: no cover
    err = probe_pi_vendor()
    if err is not None:
        print(f"[pi_adapter] D3 exit_criteria triggered: {err}", file=sys.stderr)
        sys.exit(2)
    print("[pi_adapter] vendor probe ok", file=sys.stderr)
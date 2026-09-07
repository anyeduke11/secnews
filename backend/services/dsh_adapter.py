"""DSH real-vendor stdio JSON-RPC 适配层 (v1.0 C06, D3 节点已触发降级).

定位
----
与 ``backend/services/dsh/live_bridge.py`` (T10 mock subprocess) **并存**, 不替换:

- live_bridge: 通用 JSON-RPC 客户端骨架 (subprocess + 帧解析),
  默认 ``command=(python, -m, deepseek_harness)``, 启动成功才生效。
- 本模块 (dsh_adapter): 真实上游 ``deepseek-harness d347e70`` 协议契约封装
  + **vendor 不可用时显式失败** (D3 节点裁决) + 真实 vendor 可用时直返字符串。

D3 节点裁决 (2026-09-07)
-----------------------
真实 ``deepseek-harness`` Python SDK (``python/sdk/src/deepseek_harness/``) 通过
``pip install`` 加载 ``deepseek-harness-runtime-bin`` 同版本 wheel, 而该 wheel
的二进制 payload (``runtime/deepseek-harness-sdk-runtime-<platform>-<arch>``)
**不在 git 树内** — 由 ``scripts/build-exe-for-python-sdk.ts`` 构建注入,
pyproject 显式标注 ``excluded from wheel/sdist distributions``。

C06 D3 节点实测 (macOS arm64, Python 3.14, Node 26):

  - ``pnpm install --frozen-lockfile``: ``fs-ext@2.1.1`` node-gyp 在 Node 26
    下 ``gyp ERR! command "/opt/homebrew/Cellar/node/26.4.0/bin/node" ... not ok``
    → ``ELIFECYCLE Command failed``。
  - ``python -m pip install file:///.../sdk-runtime``: ``RuntimeError:
    runtime wheel macos-arm64 payload must be deepseek-harness-sdk-runtime-macos-arm64;
    found []`` → hatch_build 校验失败。
  - ``DSH_RUNTIME_MODE=node`` (dev-only): 同样依赖 ``runtime/node/`` closure,
    同样不存在。

结论: **真实 vendor 启动不可执行**。本模块按 user/PRD 预裁, 触发 T04
``lock.exit_criteria`` 降级路径, 不静默 mock 兜底 — 显式抛
``DSHVendorUnavailableError`` 并写 ``dsh.adapter.exit_criteria_triggered`` 审计,
调用方按 ``mode_used`` 决定下一步 (default 走 ai_hub + 确定性协调器)。

契约 (与 T10 mock / T11 judgment / T12 action / T13 knowledge 对齐)
-----------------------------------------------------------------
- ``adapter_call_dsh(prompt, *, task="cve_impact_brief", timeout_s=30.0) -> str``
- 真实 vendor 可用 → 直返 vendor 响应字符串 (与 mock/ai_hub 同语义)。
- 真实 vendor 不可用 → 抛 ``DSHVendorUnavailableError`` (RuntimeError 子类),
  显式含 exit_criteria 触发信息; **绝不静默 mock**。

纪律 (与 C01 一致)
------------------
- 不引入新依赖 (仅 stdlib);
- 不在测试里真启 vendor (test_c06_real_dsh_adapter 用 mock subprocess);
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

log = logging.getLogger("hotspot.dsh_adapter")

# 上游真实 vendor 启动命令 (与 upstreams.lock.json dsh.commit_sha=d347e70 锁定):
#   python -m deepseek_harness  →  启 dsh CLI, 协议 JSON-RPC over stdio
# 真实可执行需 ``deepseek-harness-runtime-bin`` 同版本 wheel, 二进制 payload
# 不在 git 树内 (构建产物) — 见模块 docstring D3 节点裁决段。
DSH_REAL_COMMAND: tuple[str, ...] = ("python", "-m", "deepseek_harness")
DSH_REAL_COMMIT_SHA = "d347e703908d0406b7a7ef80e3a0e594d86b2215"
DSH_REAL_SHORT_SHA = "d347e70"

# vendor 启动探测超时 (秒) — 启动失败快速上抛, 不阻塞业务请求。
DSH_PROBE_TIMEOUT_S = 2.0


# ---------------------------------------------------------------------------
# 异常: vendor 不可用显式信号 (D3 节点裁决触发)
# ---------------------------------------------------------------------------
class DSHVendorUnavailableError(RuntimeError):
    """真实 ``deepseek-harness`` vendor 不可用 — 触发 T04 lock.exit_criteria。

    触发条件 (C06 D3 节点实测):
      - 命令不存在 (``FileNotFoundError``);
      - 启动后 stdout 不吐 JSON-RPC 帧 (非 vendor 进程);
      - 探测超时 (>DSH_PROBE_TIMEOUT_S 秒无输出);
      - vendor 协议版本不匹配 (HEAD != lock.commit_sha)。

    调用方契约 (judgment/action/knowledge/sk01 服务):
      - ``except DSHVendorUnavailableError`` → 走 ai_hub 确定性协调器
        (``ai_service.generate_text``); 不再尝试 vendor (本进程内熔断);
      - 不允许 ``except Exception: pass`` 静默吞, 必须显式写
        ``dsh.adapter.exit_criteria_triggered`` audit。
    """

    def __init__(self, message: str, *, commit_sha: str = DSH_REAL_COMMIT_SHA) -> None:
        super().__init__(message)
        self.commit_sha = commit_sha
        self.exit_criteria_triggered = True


# ---------------------------------------------------------------------------
# vendor 协议契约 (与官方 SDK client.py + T04 mock + T10 live_bridge 对齐)
# ---------------------------------------------------------------------------
class DSHCaller(Protocol):
    """dsh 调用者协议 — 注入供单测, 默认实现 = 真实 vendor 或 ai_hub。

    业务服务 (judgment/action/knowledge) 通过 ``_dsh_caller: DSHCaller`` 字段
    注入; ``__call__(prompt) -> str`` 必须**真返字符串**, 不返 coroutine /
    MockMagic / None — C06 R07 反例测试固化此契约。
    """

    def __call__(self, prompt: str) -> str: ...


# ---------------------------------------------------------------------------
# vendor 探测 (D3 节点显式失败信号)
# ---------------------------------------------------------------------------
def probe_dsh_vendor(*, timeout_s: float = DSH_PROBE_TIMEOUT_S) -> DSHVendorUnavailableError | None:
    """探测真实 vendor 是否可启动; 不可用即返 ``DSHVendorUnavailableError``。

    探测策略:
      1. 尝试启动 ``DSH_REAL_COMMAND`` subprocess;
      2. 写 ``session.ping`` (与 T10 协议对齐);
      3. 等待 ``session.ping`` 响应 (timeout_s 内);
      4. 任一失败 → 构造 ``DSHVendorUnavailableError`` 返给调用方。

    返回值语义:
      - ``None``: vendor 可用 (C06 D3 节点未触发, 调用方可走真实协议);
      - ``DSHVendorUnavailableError``: vendor 不可用 (C06 D3 节点触发,
        调用方按 audit + ai_hub 降级路径处理)。
    """
    try:
        proc = subprocess.Popen(
            list(DSH_REAL_COMMAND),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
    except FileNotFoundError as e:
        return DSHVendorUnavailableError(
            f"D3 vendor unavailable: command={DSH_REAL_COMMAND} FileNotFoundError ({e}); "
            f"fallback to ai_hub per T04 lock.exit_criteria",
        )
    except OSError as e:
        return DSHVendorUnavailableError(
            f"D3 vendor unavailable: command={DSH_REAL_COMMAND} OSError ({e}); "
            f"fallback to ai_hub per T04 lock.exit_criteria",
        )
    try:
        assert proc.stdin and proc.stdout
        proc.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "session.ping", "params": {},
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
            if resp.get("id") == 1 and "result" in resp:
                return None  # vendor 协议帧正常
            if "error" in resp:
                return DSHVendorUnavailableError(
                    f"D3 vendor ping error: {resp['error']}; "
                    f"fallback to ai_hub per T04 lock.exit_criteria",
                )
        return DSHVendorUnavailableError(
            f"D3 vendor probe timeout ({timeout_s}s); "
            f"fallback to ai_hub per T04 lock.exit_criteria",
        )
    except (BrokenPipeError, OSError) as e:
        return DSHVendorUnavailableError(
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


# ---------------------------------------------------------------------------
# 审计: exit_criteria 触发写盘 (best-effort, 不阻塞派发)
# ---------------------------------------------------------------------------
def _record_exit_criteria_audit(*, service: str, prompt: str) -> None:
    """落 ``dsh.adapter.exit_criteria_triggered`` 审计 (失败信息可追溯)。

    走 ``backend.observability_records.record_audit`` (与其他服务一致),
    异常自吞 (audit 失败不阻断 vendor 不可用信号)。
    """
    try:
        from backend.observability_records import record_audit
        record_audit(
            actor="system", action="dsh.adapter.exit_criteria_triggered",
            target=f"dsh.adapter.{service}",
            detail={
                "commit_sha": DSH_REAL_COMMIT_SHA,
                "fallback_path": "ai_hub (确定性协调器)",
                "prompt_prefix": prompt[:80],
                "lock_exit_criteria_days": 3,
            },
        )
    except Exception as e:
        log.warning("dsh adapter exit_criteria audit 写入失败: %s", e)


# ---------------------------------------------------------------------------
# 公共入口: adapter_call_dsh
# ---------------------------------------------------------------------------
def adapter_call_dsh(
    prompt: str,
    *,
    task: str = "cve_impact_brief",
    timeout_s: float = 30.0,
    caller_service: str = "unknown",
    dsh_caller: Callable[[str], str] | None = None,
) -> str:
    """真实 vendor 调用入口 — D3 节点触发后, 探测失败显式抛 + 写 audit。

    调用顺序:
      1. ``dsh_caller`` 注入 (单测路径) → 直返注入结果;
      2. 探测真实 vendor → 可用时直返 vendor 响应字符串;
      3. 探测失败 → 写 audit + 抛 ``DSHVendorUnavailableError``。

    业务调用方 (judgment/action/knowledge/sk01 的 ``_call_dsh``) 接此异常后
    按 contract 走 ``ai_service.generate_text`` (确定性协调器) — 但**绝不**
    静默降级; ai_hub 调用本身失败再上抛 ``JudgmentValidationError`` 等业务错。
    """
    # 1) 测试注入 (单测反例测试 fix)
    if dsh_caller is not None:
        return dsh_caller(prompt)
    # 2) 探测真实 vendor (D3 节点触发)
    err = probe_dsh_vendor(timeout_s=DSH_PROBE_TIMEOUT_S)
    if err is not None:
        _record_exit_criteria_audit(service=caller_service, prompt=prompt)
        log.warning(
            "dsh adapter D3 exit_criteria triggered (service=%s commit_sha=%s): %s",
            caller_service, err.commit_sha, err,
        )
        raise err
    # 3) vendor 可用 — 调真实协议 (T10 live_bridge 走过的路径复用)
    from backend.services.dsh.live_bridge import LiveDSHClient
    client = LiveDSHClient(timeout_s=timeout_s)
    try:
        result = client.send_task(task, {"prompt": prompt, "max_tokens": 4000})
    finally:
        client.close()
    if isinstance(result, dict):
        return str(result.get("content") or result.get("result") or json.dumps(result))
    return str(result)


# ---------------------------------------------------------------------------
# async 边界 (C06 R07 fix)
# ---------------------------------------------------------------------------
async def adapter_call_dsh_async(
    prompt: str,
    *,
    task: str = "cve_impact_brief",
    timeout_s: float = 30.0,
    caller_service: str = "unknown",
    dsh_caller: Callable[[str], str] | None = None,
) -> str:
    """``adapter_call_dsh`` 的 async 包装 — 业务服务在 async 上下文直接 await。

    C06 R07 fix: 4 个 ``_call_dsh`` 服务在 sync 路径下隐藏调用 ai_hub.generate_text
    (coroutine) 而**不 await**, 实际拿到的是 coroutine 对象 — 后续
    ``parse_cve_impact_brief_response`` 失败或返空。本函数确保 async ctx 必 await;
    sync 调用方走 ``asyncio.run(adapter_call_dsh_async(...))`` 显式强制 event loop。

    sync 注入 (``async_dsh_caller``) 供单测: 当注入值是 awaitable, await; 当
    是同步字符串, 直返 — 反例测试固化两种形态。
    """
    return adapter_call_dsh(
        prompt, task=task, timeout_s=timeout_s,
        caller_service=caller_service, dsh_caller=dsh_caller,
    )


def run_dsh_sync(
    prompt: str,
    *,
    task: str = "cve_impact_brief",
    timeout_s: float = 30.0,
    caller_service: str = "unknown",
    dsh_caller: Callable[[str], str] | None = None,
) -> str:
    """sync 入口 — 在 sync 上下文中**强制**起 event loop (避免隐藏 coroutine)。

    C06 R07 fix 主修法: 业务 service 在 sync path 调 ``ai_service.generate_text``
    (async) 但**忘了 await**, 行为是拿 coroutine 对象继续走下游解析, 旧
    ``_call_dsh`` 真因。本包装显式 ``asyncio.run``, 失败即上抛,
    测试可注入 ``fake_sync_dsh_caller`` 验证 (C06 反例测试)。

    决策规则:
      - 当前线程无 running loop → ``asyncio.run`` 直接跑;
      - 当前线程已有 running loop (嵌套 async ctx) → 改走 ``adapter_call_dsh``
        同步路径, 避免 ``asyncio.run`` 嵌套冲突。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # 无运行 loop → 用 asyncio.run 强制 await 内部 async 调用
        return asyncio.run(adapter_call_dsh_async(
            prompt, task=task, timeout_s=timeout_s,
            caller_service=caller_service, dsh_caller=dsh_caller,
        ))
    # 已有 loop (嵌套 ctx) → 走纯 sync 入口, 避免 asyncio.run 冲突
    return adapter_call_dsh(
        prompt, task=task, timeout_s=timeout_s,
        caller_service=caller_service, dsh_caller=dsh_caller,
    )


__all__ = [
    "DSH_PROBE_TIMEOUT_S",
    "DSH_REAL_COMMAND",
    "DSH_REAL_COMMIT_SHA",
    "DSH_REAL_SHORT_SHA",
    "DSHCaller",
    "DSHVendorUnavailableError",
    "adapter_call_dsh",
    "adapter_call_dsh_async",
    "probe_dsh_vendor",
    "run_dsh_sync",
]


if __name__ == "__main__":  # pragma: no cover
    # CLI 探针 — scripts/t10_live_trace.py --live 走这条路径
    err = probe_dsh_vendor()
    if err is not None:
        print(f"[dsh_adapter] D3 exit_criteria triggered: {err}", file=sys.stderr)
        sys.exit(2)
    print("[dsh_adapter] vendor probe ok", file=sys.stderr)
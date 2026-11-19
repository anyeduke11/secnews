#!/usr/bin/env python3
"""v0.8.9 红线演练④ — L3 系统层拦截 + 告警可见 (P5 C5-1 验收)。

隔离 DB/数据目录执行, 走服务层合法通道 (非手写 SQL), 产出三类证据:

1. **系统层拦截** — plan 内合法 argv, 但副作用越界 (写 workspace 外 /
   读凭据 / 出网) → sandbox-exec 内核拒绝 (PermissionError / gaierror),
   非仅"声明层校验"。
2. **告警可见** — 越界事实进 ``observability_alerts``
   (metric=``executor.boundary_violation``, level=critical) + SSE breach。
3. **资源上限** — RLIMIT_CPU 超限 → SIGXCPU 杀进程 (rc=-24)。

用法::

    HOTSPOT_DB_PATH=/tmp/v089_drill4/hotspot.db \\
    HOTSPOT_DATA_DIR=/tmp/v089_drill4_data \\
    HOTSPOT_PI_EXECUTOR_ENABLED=true \\
    python scripts/drill_v089_c5.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WS = "workspace/p5-drill"


def _setup_workspace() -> None:
    ws = ROOT / WS
    (ws / "out").mkdir(parents=True, exist_ok=True)
    (ws / "src").mkdir(parents=True, exist_ok=True)
    (ws / "src" / "input.txt").write_text("source material\n", encoding="utf-8")


def _plan(commands: list[list[str]], **overrides) -> dict:
    plan = {
        "commands": commands,
        "writable_paths": ["out"],
        "readable_paths": ["src"],
        "network": [],
        "command_timeout_sec": 30,
        "total_timeout_sec": 120,
        "output_artifact": {"kind": "report", "title": "P5 drill", "acceptance_notes": ""},
    }
    plan.update(overrides)
    return {"status": "approved", "plan": plan, "submitted_by": "drill"}


def _seed_run(tag: str) -> str:
    """建 run 并 claim(pi) → start; 返回 running 态 run_id。

    action_id 按 tag 唯一 (v1_runs 对 (action_id, attempt) 唯一) — 复跑同一
    隔离库时不会撞上已存在的 run。
    """
    from backend.services.run_service import RunService

    svc = RunService()
    run = svc.create_or_replay(
        action_id=("P" * 20 + tag.ljust(6, "x"))[:26],
        idempotency_key=f"idem-p5-{tag}-{os.getpid()}",
        attempt=1, protocol="pi",
    )["run"]
    svc.claim(run["id"], executor="pi")
    svc.start(run["id"])
    return run["id"]


def _alerts() -> list[dict]:
    from backend.repository.db import get_connection

    rows = get_connection().execute(
        "SELECT metric, level, detail, fired_at FROM observability_alerts "
        "WHERE metric = 'executor.boundary_violation' ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def _main() -> int:
    from backend.config import config
    from backend.repository.db import init_db
    from backend.services.execution_runner import runner as runner_mod

    if not config.pi_executor_enabled:
        print("FATAL: HOTSPOT_PI_EXECUTOR_ENABLED 未开启", file=sys.stderr)
        return 2

    # 隔离库需先建表 (迁移) — 否则服务层通道无表可用。
    init_db()

    _setup_workspace()
    py = sys.executable
    report: dict = {"steps": []}

    def step(name: str, fn) -> None:
        out = fn()
        report["steps"].append({"name": name, **out})
        print(f"[{name}] {json.dumps(out, ensure_ascii=False)}")

    # ── 步骤 1: 合法执行 (基线: 沙箱不能瘫掉正常功能) ──
    def step_ok():
        run_id = _seed_run("ok")
        result = runner_mod.execute_and_settle(
            run_id,
            _plan([[py, "-c", "print(open('src/input.txt').read().strip())"]]),
            workspace=WS,
        )
        return {
            "ok": result.ok,
            "reason_code": result.reason_code,
            "run_id": run_id,
            "stdout": result.stdout.strip(),
        }

    # ── 步骤 2: 写越界 (workspace 外) → L3 内核拒绝 ──
    def step_write_escape():
        target = ROOT / "p5_escape_probe.txt"
        target.unlink(missing_ok=True)
        run_id = _seed_run("write")
        result = runner_mod.execute_and_settle(
            run_id,
            _plan([[py, "-c", f"open({str(target)!r},'w').write('x')"]]),
            workspace=WS,
        )
        escaped = target.exists()
        target.unlink(missing_ok=True)
        return {
            "ok": result.ok,
            "reason_code": result.reason_code,
            "error": (result.error or "")[:200],
            "escaped_file_created": escaped,
            "run_id": run_id,
        }

    # ── 步骤 3: 读凭据 (.env) → L3 内核拒绝 ──
    def step_read_secret():
        # 用**仓库绝对路径** — cwd 是 workspace, 相对路径 ".env" 不存在,
        # 会得到 FileNotFoundError (非权限拒绝) → 证不了沙箱生效。
        secret = str(ROOT / ".env")
        run_id = _seed_run("secret")
        result = runner_mod.execute_and_settle(
            run_id,
            _plan([[py, "-c", f"print(open({secret!r}).read()[:40])"]]),
            workspace=WS,
        )
        return {
            "ok": result.ok,
            "reason_code": result.reason_code,
            "error": (result.error or "")[:200],
            "denied_by_sandbox": "Operation not permitted" in (result.error or ""),
            "run_id": run_id,
        }

    # ── 步骤 4: 出网 → L3 内核阻断 ──
    def step_network():
        code = (
            "import socket\n"
            "try:\n"
            "    socket.create_connection(('example.com', 80), timeout=5)\n"
            "    print('NET-OK')\n"
            "except Exception as e:\n"
            "    print('NET-BLOCKED', type(e).__name__)\n"
        )
        run_id = _seed_run("net")
        result = runner_mod.execute_and_settle(
            run_id, _plan([[py, "-c", code]]), workspace=WS)
        return {
            "ok": result.ok,
            "stdout": result.stdout.strip(),
            "run_id": run_id,
        }

    # ── 步骤 5a: ulimit CPU 限额 → 内核 SIGXCPU (rc=-24) ──
    # CPU 限额 = plan.command_timeout_sec (2s); 执行体的 wall timeout 比它多
    # 2s 信号投递宽限 → 内核 SIGXCPU 先到 (否则 wall 超时抢先, 限额形同虚设)。
    def step_ulimit_cpu():
        run_id = _seed_run("ulimit")
        result = runner_mod.execute_and_settle(
            run_id,
            _plan([[py, "-c", "x=0\nwhile True:\n    x+=1"]],
                  command_timeout_sec=2, total_timeout_sec=120),
            workspace=WS,
        )
        return {
            "ok": result.ok,
            "reason_code": result.reason_code,
            "error": (result.error or "")[:200],
            "killed_by_sigxcpu": "rc=-24" in (result.error or ""),
            "run_id": run_id,
        }

    # ── 步骤 5b: 总预算超时 → E_COMMAND_TIMEOUT (与 CPU 限额是两条独立机制) ──
    def step_timeout():
        run_id = _seed_run("timeout")
        result = runner_mod.execute_and_settle(
            run_id,
            _plan([[py, "-c", "import time; time.sleep(30)"]],
                  command_timeout_sec=1, total_timeout_sec=60),
            workspace=WS,
        )
        return {
            "ok": result.ok,
            "reason_code": result.reason_code,
            "run_id": run_id,
        }

    step("1-合法执行", step_ok)
    step("2-写越界", step_write_escape)
    step("3-读凭据", step_read_secret)
    step("4-出网", step_network)
    step("5a-ulimit-CPU", step_ulimit_cpu)
    step("5b-总预算超时", step_timeout)

    alerts = _alerts()
    report["alerts"] = alerts
    print(f"[告警] executor.boundary_violation 共 {len(alerts)} 条")
    for a in alerts:
        print(f"  - {a['level']} @ {a['fired_at']} :: {a['detail'][:160]}")

    print("\n=== 演练④ 汇总 ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())

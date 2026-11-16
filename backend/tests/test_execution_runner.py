"""C4-2 执行体 — 确定性 argv 执行 / 前置拦截 / 终态语义 / L4 落账。

「为什么」: 执行体是 L2 边界的唯一实际执行通道。测试必须能证明 — 开关默认
关时不推进任何进程; 审批 plan 的命令按序执行且逐条落 L4; 越界命令在产生
副作用前被拦截; 超时/非零退出以显式原因码收口 (不 fail-open)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from backend.config import config
from backend.services import execution_runner
from backend.services.execution_plan.service import boundary_hash
from backend.services.execution_runner import ExecutorDisabledError, execute_plan
from backend.services.execution_runner import runner as runner_mod

_WS = "codegarden/demo"


def _plan(commands: list[list[str]], **overrides) -> dict:
    plan = {
        "commands": commands,
        "writable_paths": ["out"],
        "readable_paths": ["."],
        "network": [],
        "command_timeout_sec": 30,
        "total_timeout_sec": 120,
        "output_artifact": {"kind": "report", "title": "CVE brief", "acceptance_notes": ""},
    }
    plan.update(overrides)
    return {"status": "approved", "plan": plan, "submitted_by": "tester"}


@pytest.fixture(autouse=True)
def _enabled_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "pi_executor_enabled", True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / _WS).mkdir(parents=True)
    return tmp_path


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


# ---------------------------------------------------------------------------
# 开关 (默认关 = 唯一回滚点)
# ---------------------------------------------------------------------------
def test_disabled_by_default_does_not_spawn(monkeypatch):
    monkeypatch.setattr(config, "pi_executor_enabled", False)
    with pytest.raises(ExecutorDisabledError):
        execute_plan("run-1", _plan([_py("print(1)")]), workspace=_WS)


# ---------------------------------------------------------------------------
# 正常路径: 按序执行 + 逐条落 agent_runs
# ---------------------------------------------------------------------------
def test_executes_commands_in_order_and_records_each(monkeypatch):
    records: list[dict] = []
    monkeypatch.setattr(runner_mod, "start_agent_run",
                        lambda **kw: records.append({"kind": "start", **kw}) or len(records))
    monkeypatch.setattr(runner_mod, "finish_agent_run",
                        lambda rowid, **kw: records.append({"kind": "finish", "id": rowid, **kw}))

    envelope = _plan([_py("print('a')"), _py("print('b')")], writable_paths=["out", "logs"])
    result = execute_plan("run-1", envelope, workspace=_WS)

    assert result.ok is True and result.reason_code is None
    assert [c.stdout_tail for c in result.commands] == ["a", "b"]   # 顺序即 plan 顺序
    assert all(c.exit_code == 0 for c in result.commands)
    assert result.boundary_hash == boundary_hash(envelope["plan"])   # L4 指纹
    assert [r["kind"] for r in records] == ["start", "finish"] * 2
    assert all(r.get("task_kind") == "run:run-1" for r in records if r["kind"] == "start")


# ---------------------------------------------------------------------------
# L2 前置拦截: 即便进了审批 plan, 静态白名单外命令仍在执行前被拦
# ---------------------------------------------------------------------------
def test_out_of_allowlist_command_intercepted_before_side_effect(tmp_path):
    marker = tmp_path / _WS / "touched"
    envelope = _plan([_py("print('ok')"), ["curl", "-o", str(marker), "https://example.com"]])
    result = execute_plan("run-1", envelope, workspace=_WS)

    assert result.ok is False
    assert result.reason_code == "E_ARGV_NOT_ALLOWED"
    assert [c.argv[0] for c in result.commands] == [sys.executable]   # 越界条从未执行
    assert not marker.exists()


def test_unapproved_plan_is_not_executed():
    envelope = _plan([_py("print('x')")])
    envelope["status"] = "draft"
    result = execute_plan("run-1", envelope, workspace=_WS)
    assert result.ok is False
    assert result.reason_code == "E_PLAN_NOT_APPROVED"
    assert result.commands == []


# ---------------------------------------------------------------------------
# 终态语义: 非零退出 / 超时 → 显式原因码, 后续命令不再执行
# ---------------------------------------------------------------------------
def test_nonzero_exit_stops_remainder():
    result = execute_plan(
        "run-1", _plan([_py("import sys; sys.exit(3)"), _py("print('never')")]),
        workspace=_WS)
    assert result.ok is False and result.reason_code == "E_COMMAND_FAILED"
    assert len(result.commands) == 1
    assert result.commands[0].exit_code == 3


def test_command_timeout_marked():
    result = execute_plan(
        "run-1",
        _plan([_py("import time; time.sleep(5)")], command_timeout_sec=1),
        workspace=_WS)
    assert result.ok is False and result.reason_code == "E_COMMAND_TIMEOUT"
    assert result.commands[0].timed_out is True


def test_workspace_outside_lock_never_spawns():
    result = execute_plan("run-1", _plan([_py("print('x')")]), workspace="/tmp")
    assert result.ok is False and result.reason_code == "E_WORKSPACE_INVALID"
    assert result.commands == []


def test_package_exports_public_entry():
    assert execution_runner.execute_plan is execute_plan
    assert execution_runner.execute_and_settle is runner_mod.execute_and_settle


# ---------------------------------------------------------------------------
# C4-3 终态回写 + 产物登记 (为什么: 执行体必须把 run 推进到显式终态, 且
# success 必须有真实落盘产物 — RA-9 禁止"成功但无产物")
# ---------------------------------------------------------------------------
def _seed_running_run() -> str:
    """建 run 并 claim(pi) → start; 返回 running 态 run_id。"""
    from backend.services.run_service import RunService

    svc = RunService()
    run = svc.create_or_replay(
        action_id="A" * 26, idempotency_key="idem-c43", attempt=1, protocol="pi",
    )["run"]
    svc.claim(run["id"], executor="pi")
    svc.start(run["id"])
    return run["id"]


def _get_run(run_id: str) -> dict:
    from backend.repository.run_repo import RunRepository

    return RunRepository().get(run_id)


def test_settle_done_registers_artifact_and_terminal_state(temp_db):
    from pathlib import Path

    from backend.repository.artifact_repo import ArtifactRepository

    run_id = _seed_running_run()
    body = "# CVE brief\n\nfull stdout body"
    result = runner_mod.execute_and_settle(
        run_id, _plan([_py(f"print({body!r})")]), workspace=_WS)

    assert result.ok is True
    run = _get_run(run_id)
    assert (run["status"], run["outcome"]) == ("succeeded", "done")
    artifact_ids = ArtifactRepository().ids_by_run(run_id)
    assert len(artifact_ids) == 1 and run["artifact_ids"] == artifact_ids
    art = ArtifactRepository().get(artifact_ids[0])
    assert (art["kind"], art["title"]) == ("report", "CVE brief")
    # 落盘正文 = 末条命令完整 stdout (R08: content_ref 可读回)
    assert Path(art["content_ref"]).read_text(encoding="utf-8").strip() == body


def test_settle_failure_marks_run_failed_with_reason(temp_db):
    from backend.repository.artifact_repo import ArtifactRepository

    run_id = _seed_running_run()
    result = runner_mod.execute_and_settle(
        run_id, _plan([_py("import sys; sys.exit(3)")]), workspace=_WS)

    assert result.ok is False
    run = _get_run(run_id)
    assert (run["status"], run["outcome"]) == ("failed", "failed")
    assert "E_COMMAND_FAILED" in run["error"]
    assert ArtifactRepository().ids_by_run(run_id) == []


def test_settle_timeout_maps_to_timed_out(temp_db):
    run_id = _seed_running_run()
    result = runner_mod.execute_and_settle(
        run_id, _plan([_py("import time; time.sleep(5)")], command_timeout_sec=1),
        workspace=_WS)

    assert result.reason_code == "E_COMMAND_TIMEOUT"
    run = _get_run(run_id)
    assert (run["status"], run["outcome"]) == ("timed_out", "timeout")
    assert "E_COMMAND_TIMEOUT" in run["error"]


def test_settle_out_of_plan_command_marks_run_failed(temp_db):
    """C4-4 验收前置: 越界拦截后 run 必须显式 failed + 原因码 (不静默)。"""
    from backend.repository.artifact_repo import ArtifactRepository

    run_id = _seed_running_run()
    result = runner_mod.execute_and_settle(
        run_id, _plan([["curl", "https://example.com"]]), workspace=_WS)

    assert result.reason_code == "E_ARGV_NOT_ALLOWED"
    run = _get_run(run_id)
    assert (run["status"], run["outcome"]) == ("failed", "failed")
    assert "E_ARGV_NOT_ALLOWED" in run["error"]
    assert ArtifactRepository().ids_by_run(run_id) == []


def test_settle_empty_stdout_fails_without_fake_artifact(temp_db):
    from backend.repository.artifact_repo import ArtifactRepository

    run_id = _seed_running_run()
    result = runner_mod.execute_and_settle(
        run_id, _plan([_py("pass")]), workspace=_WS)

    assert result.ok is False and result.reason_code == "E_ARTIFACT_EMPTY"
    run = _get_run(run_id)
    assert (run["status"], run["outcome"]) == ("failed", "failed")
    assert ArtifactRepository().ids_by_run(run_id) == []


# ---------------------------------------------------------------------------
# C5-1 L3 系统层接线 + 越界告警
#
# 「为什么」: P4 只做了声明级拦截 (L2), 越界事实只落在 run.error — 运维侧
# 无主动可见性。本组锁死: ① L3 sandbox 生效时命令真的在系统层受限;
# ② 越界事实进 observability_alerts (告警可见 = PRD R-4 ③ 验收);
# ③ 普通命令失败**不**告警 (否则噪声淹没真越界)。
# ---------------------------------------------------------------------------
def _alerts(metric: str) -> list:
    from backend.repository import db

    return db.get_connection().execute(
        "SELECT level, detail FROM observability_alerts WHERE metric = ?",
        (metric,),
    ).fetchall()


def test_l2_violation_emits_boundary_alert(temp_db):
    """L2 越界 (argv 不在 plan) → boundary_violation 告警落表 + 可见。"""
    result = execute_plan("run-1", _plan([["curl", "https://example.com"]]), workspace=_WS)

    assert result.reason_code == "E_ARGV_NOT_ALLOWED"
    rows = _alerts("executor.boundary_violation")
    assert len(rows) == 1 and rows[0]["level"] == "critical"
    assert "E_ARGV_NOT_ALLOWED" in rows[0]["detail"]


def test_boundary_alerts_from_different_runs_are_not_suppressed(temp_db):
    """跨 run 的真实越界各自可见 — 演练④ 实测: 全局 cooldown 会吞掉跨 run 越界。

    同 (metric, level) 的 cooldown 若不加去重维度, 一个窗口内只有第一条
    越界可见 → 违反「失败必可见」。dedupe_key=run_id 后: 不同 run 各自落一条。
    """
    execute_plan("run-a", _plan([["curl", "https://example.com"]]), workspace=_WS)
    execute_plan("run-b", _plan([["curl", "https://example.com"]]), workspace=_WS)

    rows = _alerts("executor.boundary_violation")
    assert len(rows) == 2
    run_ids = {json.loads(r["detail"])["run_id"] for r in rows}
    assert len(run_ids) == 2   # 两条告警指向不同 run


def test_boundary_alert_dedupes_within_same_run(temp_db):
    """同一 run 内重复越界合并 — 不刷屏。"""
    for _ in range(3):
        execute_plan("run-same", _plan([["curl", "https://example.com"]]), workspace=_WS)

    assert len(_alerts("executor.boundary_violation")) == 1


def test_plain_command_failure_does_not_emit_boundary_alert(temp_db):
    """普通非零退出不是越界 — 不告警 (避免噪声淹没真越界)。"""
    result = execute_plan("run-1", _plan([_py("import sys; sys.exit(3)")]), workspace=_WS)

    assert result.reason_code == "E_COMMAND_FAILED"
    assert _alerts("executor.boundary_violation") == []


def test_successful_run_emits_no_boundary_alert(temp_db):
    result = execute_plan("run-1", _plan([_py("print('ok')")]), workspace=_WS)

    assert result.ok is True
    assert _alerts("executor.boundary_violation") == []


def test_sandbox_constraints_recorded_in_audit_log(temp_db):
    """L4 留痕: 本 run 生效的系统层约束落 audit_log (可复现边界)。"""
    execute_plan("run-1", _plan([_py("print('ok')")]), workspace=_WS)

    from backend.repository import db

    rows = db.get_connection().execute(
        "SELECT detail FROM audit_log WHERE action = 'executor.sandbox'"
    ).fetchall()
    assert len(rows) == 1
    assert "sandbox" in rows[0]["detail"]


@pytest.mark.skipif(
    not runner_mod.sandbox_supported(), reason="sandbox-exec 仅 macOS 可用"
)
def test_l3_sandbox_blocks_write_outside_declared_paths(temp_db):
    """L3 系统层: 命令在 plan 内 (argv 合法) 但写 workspace 外 → 内核拒绝。

    这是 L2 拦不住的情形 (argv 合法, 只是副作用越界) — 正是 P5 的价值。
    """
    marker = Path(_enabled_workspace_root()) / "escaped.txt"
    result = execute_plan(
        "run-1",
        _plan([_py("open('escaped.txt','w').write('x')")]),
        workspace=_WS,
    )

    assert result.ok is False
    assert not marker.exists()


def _enabled_workspace_root() -> str:
    import os

    return os.path.join(os.getcwd(), _WS)


def test_degrades_when_sandbox_unavailable(monkeypatch, temp_db):
    """非 macOS (无 sandbox-exec) → 降级为「仅 ulimit」, 不崩不留白。

    降级必须是**显式**的: 记 warning + 不假装有沙箱 (审计 detail 记
    sandbox=unavailable), 而不是静默按无约束执行。
    """
    monkeypatch.setattr(runner_mod, "sandbox_supported", lambda: False)
    result = execute_plan("run-1", _plan([_py("print('ok')")]), workspace=_WS)

    assert result.ok is True
    from backend.repository import db

    rows = db.get_connection().execute(
        "SELECT detail FROM audit_log WHERE action = 'executor.sandbox'"
    ).fetchall()
    # 降级时仍留痕 — 但明确标记 sandbox 不可用
    assert len(rows) == 1 and '"sandbox": "unavailable"' in rows[0]["detail"]
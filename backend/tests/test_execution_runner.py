"""C4-2 执行体 — 确定性 argv 执行 / 前置拦截 / 终态语义 / L4 落账。

「为什么」: 执行体是 L2 边界的唯一实际执行通道。测试必须能证明 — 开关默认
关时不推进任何进程; 审批 plan 的命令按序执行且逐条落 L4; 越界命令在产生
副作用前被拦截; 超时/非零退出以显式原因码收口 (不 fail-open)。
"""
from __future__ import annotations

import sys

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